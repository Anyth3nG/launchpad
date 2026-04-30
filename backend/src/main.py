"""Entry point for the Launchpad FastAPI backend."""

import docker
import docker.errors
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Launchpad", version="0.1.0")


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
