"""Entry point for the Launchpad FastAPI backend."""

import shutil
from pathlib import Path
from urllib.parse import urlparse

import docker
import docker.errors
import git
import git.exc
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Launchpad", version="0.1.0")

TMP_DIR = Path(__file__).parent.parent / "tmp"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    """Payload for the /build-service endpoint."""

    repo_url: str


class DeployRequest(BaseModel):
    """Payload for the /container-deployment endpoint."""

    repo: str  # Accepts 'owner/repo' or 'owner-repo'


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Return service health status. No authentication required."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/docker-status", tags=["docker"])
async def docker_status() -> JSONResponse:
    """List and inspect all running containers via the Docker SDK.

    Returns a list of running containers, each with their id, status,
    image name, and port mappings. Returns 503 if Docker is unreachable
    and an empty list if Docker is running but no containers are active.
    """
    try:
        client = docker.from_env()
        containers = client.containers.list()
    except docker.errors.DockerException:
        return JSONResponse(
            status_code=503,
            content={"error": "Docker daemon is not reachable"},
        )

    if not containers:
        return JSONResponse(content={"containers": []})

    result = []
    for container in containers:
        result.append({
            "container_id": container.short_id,
            "status": container.status,
            "image": container.image.tags[0] if container.image.tags else container.image.short_id,
            "ports": _format_ports(container.ports),
        })

    return JSONResponse(content={"containers": result})


@app.post("/build-service", tags=["build"])
async def build_service(request: BuildRequest) -> JSONResponse:
    """Clone a public GitHub repository and build a Docker image from its Dockerfile.

    Validates the URL is a GitHub repo, checks the repo exists, clones it into
    a temporary directory, verifies a Dockerfile is present, then builds and tags
    the image. The temporary clone is always removed after the build attempt.
    """
    if not _is_github_url(request.repo_url):
        return JSONResponse(
            status_code=400,
            content={"error": "URL must point to a GitHub repository (https://github.com/owner/repo)"},
        )

    owner, repo_name = _extract_repo_info(request.repo_url)
    if not owner or not repo_name:
        return JSONResponse(
            status_code=400,
            content={"error": "Could not parse owner and repository name from URL"},
        )

    # Verify repo exists on GitHub before attempting a clone
    async with httpx.AsyncClient() as http:
        try:
            gh_response = await http.get(
                f"https://api.github.com/repos/{owner}/{repo_name}",
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
        except httpx.RequestError:
            return JSONResponse(
                status_code=502,
                content={"error": "Could not reach GitHub API to verify repository"},
            )

    if gh_response.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={"error": f"Repository '{owner}/{repo_name}' not found on GitHub"},
        )
    if gh_response.status_code != 200:
        return JSONResponse(
            status_code=502,
            content={"error": "GitHub API returned an unexpected response"},
        )

    # Clone into tmp/<owner>-<repo_name>; always clean up afterwards
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    clone_path = TMP_DIR / f"{owner}-{repo_name}"

    if clone_path.exists():
        shutil.rmtree(clone_path)

    try:
        git.Repo.clone_from(request.repo_url, str(clone_path))
    except git.exc.GitCommandNotFound:
        return JSONResponse(
            status_code=500,
            content={"error": "Git is not installed on this server"},
        )
    except git.exc.GitCommandError as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to clone repository: {str(e).strip()}"},
        )

    try:
        if not (clone_path / "Dockerfile").exists():
            return JSONResponse(
                status_code=422,
                content={"error": f"No Dockerfile found in '{owner}/{repo_name}'"},
            )

        image_tag = f"launchpad/{owner.lower()}-{repo_name.lower()}:latest"

        try:
            docker_client = docker.from_env()
            image, _ = docker_client.images.build(
                path=str(clone_path),
                tag=image_tag,
                rm=True,
            )
        except docker.errors.BuildError as e:
            build_log = "\n".join(
                line.get("stream", "").strip()
                for line in e.build_log
                if line.get("stream", "").strip()
            )
            return JSONResponse(
                status_code=500,
                content={"error": "Docker build failed", "details": build_log},
            )
        except docker.errors.APIError as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Docker API error: {e.explanation}"},
            )
        except docker.errors.DockerException as e:
            return JSONResponse(
                status_code=503,
                content={"error": f"Docker daemon is not reachable: {str(e)}"},
            )
    finally:
        shutil.rmtree(clone_path, ignore_errors=True)

    return JSONResponse(
        status_code=201,
        content={
            "message": "Image built successfully",
            "image": image_tag,
            "repo": f"{owner}/{repo_name}",
        },
    )


@app.post("/container-deployment", tags=["run"])
async def container_deployment(request: DeployRequest) -> JSONResponse:
    """Deploy a pre-built image as a container with enforced resource limits.

    Accepts a repo identifier ('owner/repo' or 'owner-repo') and looks for a
    matching image built by /build-service. If found, starts the container with
    512 MB memory and 0.5 CPU limits, publishes all exposed ports to random
    available host ports, and returns the container ID, name, and port mappings.
    Returns 404 if no matching image exists.
    """
    repo_key = request.repo.lower().replace("/", "-").strip()
    expected_tag = f"launchpad/{repo_key}:latest"

    try:
        docker_client = docker.from_env()
        all_images = docker_client.images.list()
    except docker.errors.DockerException:
        return JSONResponse(
            status_code=503,
            content={"error": "Docker daemon is not reachable"},
        )

    matched = any(expected_tag in (img.tags or []) for img in all_images)

    if not matched:
        available = [
            tag
            for img in all_images
            for tag in (img.tags or [])
            if tag.startswith("launchpad/")
        ]
        return JSONResponse(
            status_code=404,
            content={
                "error": f"No built image found for '{request.repo}'. "
                         "Build it first using /build-service.",
                "available_images": available,
            },
        )

    try:
        container = docker_client.containers.run(
            image=expected_tag,
            detach=True,
            publish_all_ports=True,
            mem_limit="512m",
            nano_cpus=500_000_000,  # 0.5 CPU cores
        )
    except docker.errors.ImageNotFound:
        return JSONResponse(
            status_code=404,
            content={"error": f"Image '{expected_tag}' not found"},
        )
    except docker.errors.APIError as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Docker failed to start the container", "details": e.explanation},
        )
    except docker.errors.DockerException as e:
        return JSONResponse(
            status_code=503,
            content={"error": f"Docker daemon is not reachable: {str(e)}"},
        )

    container.reload()
    assigned_ports = _format_ports(container.ports)

    return JSONResponse(
        status_code=201,
        content={
            "message": "Container deployed successfully",
            "container_id": container.short_id,
            "container_name": container.name,
            "ports": assigned_ports if assigned_ports else "no ports exposed by this image",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_ports(ports: dict) -> list[str]:
    """Convert Docker SDK port dict into readable 'host:container/proto' strings."""
    formatted = []
    for container_port, host_bindings in ports.items():
        if host_bindings:
            for binding in host_bindings:
                formatted.append(f"{binding['HostPort']}:{container_port}")
        else:
            formatted.append(container_port)
    return formatted


def _is_github_url(url: str) -> bool:
    """Return True if the URL points to github.com over http/https."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("https", "http") and parsed.netloc in ("github.com", "www.github.com")
    except Exception:
        return False


def _extract_repo_info(url: str) -> tuple[str, str] | tuple[None, None]:
    """Parse owner and repo name from a GitHub URL.

    Handles both https://github.com/owner/repo and .git suffixed variants.
    """
    try:
        path = urlparse(url).path.strip("/").removesuffix(".git")
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
    except Exception:
        pass
    return None, None
