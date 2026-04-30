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

\* Auth not yet implemented — will require bearer token in a future ticket.

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
