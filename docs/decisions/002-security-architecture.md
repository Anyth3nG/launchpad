# ADR 002 — Security Architecture

**Date:** [29.04.2026]  
**Status:** Accepted

## Context

MyPaaS accepts arbitrary GitHub repositories and builds them as 
containers. This is a high-risk operation. A compromised build 
pipeline can lead to arbitrary code execution on the host machine.

## Decisions

### API Authentication
All API endpoints require a bearer token. No public unauthenticated 
endpoints except the GitHub webhook (which uses HMAC verification instead).

### GitHub Webhook Verification
Every incoming webhook request must include a valid HMAC-SHA256 
signature using a shared secret. Requests without a valid signature 
are rejected with 401 before any processing occurs.

### Container Isolation
All user containers run with:
- No privileged mode (`--privileged` is never used)
- No host network access (default bridge network only)
- CPU limit: 0.5 cores per container
- Memory limit: 512MB per container
- Read-only root filesystem where possible
- No access to host filesystem mounts

### Least Privilege
- FastAPI backend does not run as root
- PostgreSQL user has only SELECT/INSERT/UPDATE/DELETE — no DDL
- Docker socket access is restricted to the backend process only

### Rate Limiting
API endpoints are rate limited per IP:
- General endpoints: 60 requests/minute
- Deployment trigger endpoints: 5 requests/minute
- Auth failures: lockout after 10 consecutive failures

### Request Logging
All requests are logged with: timestamp, IP, endpoint, 
response code, and authenticated user. Logs do not contain 
request bodies (which may contain secrets).

## What is explicitly out of scope (for now)
- Multi-tenant isolation (this is a single-user platform)
- Secret scanning on submitted repos
- Network egress filtering for containers
