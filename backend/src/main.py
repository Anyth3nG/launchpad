"""Entry point for the Launchpad FastAPI backend."""

import os
import shutil
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

import docker
import docker.errors
import git
import git.exc
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv(Path(__file__).parent.parent.parent / ".env")

app = FastAPI(title="Launchpad", version="0.1.0")

TMP_DIR = Path(__file__).parent.parent / "tmp"

# ---------------------------------------------------------------------------
# Rate limiting config
# ---------------------------------------------------------------------------

_WINDOW_SECONDS = 60
_GENERAL_LIMIT = 60        # requests per minute for general endpoints
_DEPLOY_LIMIT = 5          # requests per minute for deployment endpoints
_AUTH_LOCKOUT_LIMIT = 10   # consecutive auth failures before lockout
_AUTH_LOCKOUT_SECONDS = 900  # lockout duration: 15 minutes

_DEPLOY_ENDPOINTS = {"/build-service", "/container-deployment"}
_EXEMPT_ENDPOINTS = {"/health"}

# In-memory sliding window state (process-local, resets on restart)
# Keyed by (ip, tier) so deployment and general windows are tracked independently
_request_log: dict[tuple[str, str], deque] = defaultdict(deque)
_auth_failures: dict[str, int] = defaultdict(int)   # ip -> consecutive 401 count
_lockout_start: dict[str, float] = {}                # ip -> timestamp when lockout began


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-IP rate limits and auth failure lockout on all endpoints.

    General endpoints are limited to 60 requests/minute. Deployment endpoints
    (/build-service, /container-deployment) are limited to 5 requests/minute.
    /health is exempt. IPs are locked out after 10 consecutive auth failures.
    """

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        """Check rate limits before passing the request, track auth failures after."""
        ip = _get_client_ip(request)
        path = request.url.path

        if path in _EXEMPT_ENDPOINTS:
            return await call_next(request)

        # Auth failure lockout — expires after 15 minutes automatically
        if _auth_failures[ip] >= _AUTH_LOCKOUT_LIMIT:
            lockout_age = time.time() - _lockout_start.get(ip, 0)
            if lockout_age < _AUTH_LOCKOUT_SECONDS:
                retry_after = int(_AUTH_LOCKOUT_SECONDS - lockout_age) + 1
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too many authentication failures. IP temporarily locked out.",
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            # Lockout expired — reset and allow the request through
            _auth_failures[ip] = 0
            _lockout_start.pop(ip, None)

        # Sliding window rate limit — keyed by (ip, tier) to keep windows independent
        tier = "deploy" if path in _DEPLOY_ENDPOINTS else "general"
        limit = _DEPLOY_LIMIT if tier == "deploy" else _GENERAL_LIMIT
        now = time.time()
        window_start = now - _WINDOW_SECONDS
        timestamps = _request_log[(ip, tier)]

        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= limit:
            retry_after = int(_WINDOW_SECONDS - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": _WINDOW_SECONDS,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        response = await call_next(request)

        # Track consecutive auth failures; record lockout start when threshold is first hit
        if response.status_code == 401:
            _auth_failures[ip] += 1
            if _auth_failures[ip] >= _AUTH_LOCKOUT_LIMIT and ip not in _lockout_start:
                _lockout_start[ip] = time.time()
        elif response.status_code < 400:
            _auth_failures[ip] = 0
            _lockout_start.pop(ip, None)

        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Validate the Bearer token on every request except /health.

    Reads TOKEN_BEARER from the environment at startup. Requests without an
    Authorization header return 401. Requests with a token that does not match
    return 403. /health is exempt and requires no token.
    """

    def __init__(self, app):
        """Load the expected bearer token from the environment."""
        super().__init__(app)
        self._token = os.environ.get("TOKEN_BEARER", "")
        if not self._token:
            raise RuntimeError("TOKEN_BEARER is not set in the environment")

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        """Check the Authorization header before passing the request."""
        if request.url.path in _EXEMPT_ENDPOINTS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing Authorization header. Expected: Bearer <token>"},
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return JSONResponse(
                status_code=401,
                content={"error": "Malformed Authorization header. Expected: Bearer <token>"},
            )

        if parts[1] != self._token:
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid token"},
            )

        return await call_next(request)


# Middleware is executed in reverse registration order.
# AuthMiddleware is added first (inner), RateLimitMiddleware second (outer).
# Execution order: RateLimit → Auth → endpoint.
# This means RateLimitMiddleware sees the 401/403 responses from AuthMiddleware
# and can correctly count them toward the auth failure lockout.
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    """Payload for the /build-service endpoint."""

    repo_url: str


class DeployRequest(BaseModel):
    """Payload for the /container-deployment endpoint."""

    repo: str  # Accepts 'owner/repo' or 'owner-repo'


class StopRequest(BaseModel):
    """Payload for the /stop-service endpoint."""

    identifier: str  # Container ID, container name, repo name, or image tag


class RemoveRequest(BaseModel):
    """Payload for the /remove-service endpoint."""

    identifier: str  # Container ID, container name, repo name, or image tag
    force: bool = False  # Stop the container first if it is still running


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


@app.post("/stop-service", tags=["run"])
async def stop_service(request: StopRequest) -> JSONResponse:
    """Stop a running container identified by container ID, name, or repo name.

    Looks up the container using the identifier (tried as a direct Docker ID/name
    first, then as a repo-derived image tag). Returns 409 if the container is
    already stopped, and 404 if no matching container is found.
    """
    try:
        docker_client = docker.from_env()
    except docker.errors.DockerException:
        return JSONResponse(
            status_code=503,
            content={"error": "Docker daemon is not reachable"},
        )

    container = _resolve_container(docker_client, request.identifier)

    if container is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"No container found for '{request.identifier}'"},
        )

    if container.status != "running":
        return JSONResponse(
            status_code=409,
            content={
                "error": f"Container '{container.name}' is not running (status: {container.status})",
                "container_id": container.short_id,
                "container_name": container.name,
            },
        )

    try:
        container.stop()
    except docker.errors.APIError as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to stop container", "details": e.explanation},
        )

    return JSONResponse(
        content={
            "message": "Container stopped successfully",
            "container_id": container.short_id,
            "container_name": container.name,
        },
    )


@app.post("/remove-service", tags=["run"])
async def remove_service(request: RemoveRequest) -> JSONResponse:
    """Remove a container identified by container ID, name, or repo name.

    If the container is still running and force=false, returns 409 with a prompt
    to stop it first. If force=true, stops the container before removing it.
    Returns 404 if no matching container is found.
    """
    try:
        docker_client = docker.from_env()
    except docker.errors.DockerException:
        return JSONResponse(
            status_code=503,
            content={"error": "Docker daemon is not reachable"},
        )

    container = _resolve_container(docker_client, request.identifier)

    if container is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"No container found for '{request.identifier}'"},
        )

    if container.status == "running":
        if not request.force:
            return JSONResponse(
                status_code=409,
                content={
                    "error": (
                        f"Container '{container.name}' is still running. "
                        "Stop it first using /stop-service, or pass force=true to stop and remove in one step."
                    ),
                    "container_id": container.short_id,
                    "container_name": container.name,
                },
            )

        try:
            container.stop()
        except docker.errors.APIError as e:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to stop container before removal", "details": e.explanation},
            )

    try:
        container.remove()
    except docker.errors.APIError as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to remove container", "details": e.explanation},
        )

    return JSONResponse(
        content={
            "message": "Container removed successfully",
            "container_id": container.short_id,
            "container_name": container.name,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Return the real client IP, preferring X-Forwarded-For set by Nginx."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _resolve_container(client: docker.DockerClient, identifier: str):
    """Find a container by ID, name, or repo-derived image tag.

    Tries a direct Docker lookup first (handles full/short IDs and names).
    Falls back to treating the identifier as a repo name and searching all
    containers (including stopped ones) for a matching launchpad/ image tag.
    Returns the Container object, or None if nothing matched.
    """
    try:
        return client.containers.get(identifier)
    except docker.errors.NotFound:
        pass

    repo_key = identifier.lower().replace("/", "-").strip()
    image_tag = f"launchpad/{repo_key}:latest"

    for container in client.containers.list(all=True):
        try:
            tags = container.image.tags or []
        except docker.errors.ImageNotFound:
            # Image was deleted after the container was created; skip safely
            continue
        if image_tag in tags:
            return container

    return None


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
