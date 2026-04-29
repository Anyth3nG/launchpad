# MyPaaS — Claude Code Context

## What this project is
A self-hosted PaaS that builds and deploys GitHub repositories as 
Docker containers. Think stripped-down Railway/Render.

## Stack
- Backend: FastAPI (Python)
- Database: PostgreSQL with SQLAlchemy
- Frontend: React
- Containers: Docker Engine + Docker SDK for Python
- Reverse proxy: Nginx
- CI/CD: GitHub Actions

## Project structure
- /backend — FastAPI application
- /frontend — React dashboard
- /cli — CLI tool
- /nginx — Nginx configuration
- /docs — Architecture docs, ADRs, runbooks

## Rules Claude Code must follow
- Every feature maps to a GitHub issue number — reference it in commits
- No hardcoded secrets or credentials anywhere
- All containers run without privileged mode
- Database credentials come from environment variables only
- Follow existing file structure — don't invent new top-level folders
- Write docstrings on all functions
- All endpoints require authentication except /health and /webhook

## Security requirements
See docs/decisions/002-security-architecture.md
See docs/threat-model.md

## Before writing any code
Read the relevant ADR in docs/decisions/ first.
