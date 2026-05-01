# Runbooks

Operational procedures for MyPaaS.

---

## Deploy a repository

### 1. Build the image

```bash
curl -X POST http://localhost:8000/build-service \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repo"}'
```

Expected response (`201`):
```json
{
  "message": "Image built successfully",
  "image": "launchpad/owner-repo:latest",
  "repo": "owner/repo"
}
```

Common errors:
- `400` — URL is not a valid GitHub URL
- `404` — Repository not found on GitHub
- `422` — Repository has no `Dockerfile` at its root
- `500` — Docker build failed (response includes build log)

### 2. Deploy the container

```bash
curl -X POST http://localhost:8000/container-deployment \
  -H "Content-Type: application/json" \
  -d '{"repo": "owner/repo"}'
```

Expected response (`201`):
```json
{
  "message": "Container deployed successfully",
  "container_id": "a3f9c2d1b",
  "container_name": "romantic_turing",
  "ports": ["32768:8080/tcp"]
}
```

Use the `container_id` or `container_name` to manage the container with `docker` CLI commands.

Common errors:
- `404` — No built image found. Run step 1 first. The response includes `available_images` listing what is ready.
- `500` — Docker failed to start the container (response includes details)

### 3. Verify it is running

```bash
curl http://localhost:8000/docker-status
```

---

## Stop a running container

```bash
docker stop <container_name_or_id>
```

---

## Check container resource usage

```bash
docker stats <container_name_or_id>
```

All containers are limited to 512 MB memory and 0.5 CPU cores. If a container is hitting its memory limit it will appear in `docker stats` near 100% of its `MEM LIMIT`.
