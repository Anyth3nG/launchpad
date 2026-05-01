# Backend

FastAPI backend for Launchpad.

## Running locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in real values
uvicorn src.main:app --reload
```

The API will be available at http://localhost:8000.  
Interactive docs at http://localhost:8000/docs.

## Running with Docker

```bash
docker build -t launchpad-backend .
docker run --env-file .env -p 8000:8000 launchpad-backend
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /health | None | Service health check |
| GET | /docker-status | None* | List all running containers |
| POST | /build-service | None* | Clone a GitHub repo and build a Docker image |
| POST | /container-deployment | None* | Deploy a built image as a resource-limited container |

\* Auth not yet implemented — will require bearer token in a future ticket.

## Build service

`POST /build-service` accepts a JSON body:

```json
{ "repo_url": "https://github.com/owner/repo" }
```

The endpoint:
1. Validates the URL is a GitHub URL
2. Checks the repository exists via the GitHub API
3. Clones the repo into `backend/tmp/<owner>-<repo>/`
4. Verifies a `Dockerfile` exists at the repo root
5. Builds and tags the image as `launchpad/<owner>-<repo>:latest`
6. Deletes the temporary clone regardless of build outcome

The `tmp/` directory is git-ignored and never committed.

## Run service

`POST /container-deployment` accepts a JSON body:

```json
{ "repo": "owner/repo" }
```

Both `"owner/repo"` and `"owner-repo"` formats are accepted.

The endpoint:
1. Normalises the repo identifier and looks for a matching `launchpad/<owner>-<repo>:latest` image
2. Returns 404 with a list of available built images if no match is found
3. Starts the container with enforced resource limits (see table below)
4. Uses `publish_all_ports=True` so Docker auto-assigns an available host port for every `EXPOSE`'d container port
5. Returns `container_id`, `container_name`, and `ports` on success

### Resource limits

| Resource | Limit |
|----------|-------|
| Memory | 512 MB |
| CPU | 0.5 cores |
| Privileged mode | Never |
| Network | Bridge (default) |

### Example response

```json
{
  "message": "Container deployed successfully",
  "container_id": "a3f9c2d1b",
  "container_name": "romantic_turing",
  "ports": ["32768:8080/tcp"]
}
```

If the image has no `EXPOSE` directives, `ports` will be `"no ports exposed by this image"`.

## Docker socket access

`/docker-status` talks to the Docker daemon via the Docker SDK. When running
locally the SDK connects through `/var/run/docker.sock` automatically.

When running inside Docker you must bind-mount the socket:

```bash
docker run --env-file .env -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  launchpad-backend
```

The socket is never exposed publicly — only the backend process has access to it,
per the security architecture in `docs/decisions/002-security-architecture.md`.
