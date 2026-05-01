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

## Request Flow — New Deployment
```bash
User/GitHub Webhook
│
▼
Nginx (proxy)
│
▼
FastAPI Backend
│
├──► PostgreSQL (create deployment record)
│
├──► Docker (build image from repo)
│
├──► Docker (run container)
│
├──► PostgreSQL (update status, store logs)
│
└──► Nginx config (register new route)
```
## Security boundaries

See [../threat-model.md](../threat-model.md)
