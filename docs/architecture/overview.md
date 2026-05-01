# Architecture Overview

## System Components

### Backend (FastAPI)
The core orchestration engine. Responsible for:
- Receiving deployment requests (API + webhooks)
- Calling Docker to build and run containers
- Storing deployment state in PostgreSQL
- Exposing a REST API to the dashboard and CLI

### Container Runtime (Docker)
Each deployed application runs as an isolated Docker container.
The backend communicates with Docker via the Docker SDK for Python.
All containers are resource-limited and run without elevated privileges.

### Database (PostgreSQL)
Stores persistent state:
- Deployment history
- Service metadata (name, repo URL, port, status)
- Build logs
- Health check results

### Frontend (React)
A dashboard for managing services. Communicates exclusively with the 
FastAPI backend via REST API. Never talks to Docker or PostgreSQL directly.

### Reverse Proxy (Nginx)
Routes incoming traffic to the correct running container based on 
subdomain or path. Also terminates TLS when configured.

### CLI Tool
A terminal client for the FastAPI backend. Allows deployments, 
status checks, and log viewing without the dashboard.

## Request Flow

Build and run are intentionally separate API calls. A repo must be built before it can be deployed.

### Step 1 — Build (`POST /build-service`)
```
User
│
▼
FastAPI Backend
│
├──► GitHub API (verify repo exists)
│
├──► Git (clone repo to tmp/)
│
├──► Docker (build image → launchpad/<owner>-<repo>:latest)
│
└──► tmp/ clone deleted
```

### Step 2 — Deploy (`POST /container-deployment`)
```
User
│
▼
FastAPI Backend
│
├──► Docker (find matching launchpad/ image)
│
└──► Docker (run container — 512 MB / 0.5 CPU / auto-assigned port)
```
## Security boundaries

See [../threat-model.md](../threat-model.md)
