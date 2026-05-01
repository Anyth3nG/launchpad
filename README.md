# MyPaaS

A self-hosted Platform as a Service (PaaS) for deploying containerized applications 
from GitHub repositories. Built as a learning project to understand how platforms 
like Railway and Render work under the hood.

## What it does

- Accepts a GitHub repository URL and builds it as a Docker image
- Deploys built images as containers with enforced CPU and memory resource limits
- Auto-assigns host ports so deployed services are immediately reachable
- Monitors running containers and surfaces status via a REST API
- Provides a React dashboard for managing deployments and viewing logs
- Supports GitHub webhook integration for automatic deploys on push
- Includes a CLI tool for terminal-based deployments

## Architecture overview

See [docs/architecture/overview.md](docs/architecture/overview.md)

## Tech stack

- **Backend:** FastAPI (Python)
- **Containers:** Docker Engine + Docker SDK for Python
- **Database:** PostgreSQL
- **Frontend:** React
- **Reverse Proxy:** Nginx
- **CI/CD:** GitHub Actions

## Project status

🚧 In active development — Phase 0 (Foundation)

## Running locally

Documentation coming in Phase 2.
