# ADR 001 — Tech Stack Selection

**Date:** [29.04.2026]  
**Status:** Accepted

## Decision

The following technologies were chosen for the MyPaaS platform.

## Backend: FastAPI (Python)

**Alternatives considered:** Express (Node.js), Django REST Framework  
**Reason:** FastAPI is async-native, has automatic OpenAPI/Swagger docs 
generation, and Python has the best Docker SDK support. Django was 
overkill for an API-only backend. Express would have worked but 
Python is the stronger choice for DevOps-adjacent tooling.

## Container Runtime: Docker Engine + Docker SDK for Python

**Alternatives considered:** Podman, direct shell commands  
**Reason:** Docker is the industry standard and what Railway/Render 
are built on top of. The official Python SDK (`docker` package) 
gives clean programmatic control without shelling out. Podman 
is a valid alternative but has less learning material available.

## Database: PostgreSQL

**Alternatives considered:** SQLite, MySQL  
**Reason:** PostgreSQL is the production standard for relational 
data. SQLite is not suitable for concurrent access from multiple 
processes. MySQL is viable but PostgreSQL has better JSON support 
which we may use for storing build metadata.

## Frontend: React

**Alternatives considered:** Vue, plain HTML/JS  
**Reason:** React is the dominant framework in job postings and 
industry use. The dashboard complexity (real-time log streaming, 
dynamic state) justifies using a framework over plain JS.

## Reverse Proxy: Nginx

**Alternatives considered:** Traefik, Caddy  
**Reason:** Nginx is ubiquitous and well-documented. Traefik has 
better Docker-native routing and auto-config, and may be 
considered as a Phase 2 upgrade. Nginx chosen first because 
understanding manual configuration is more educational.

## CI/CD: GitHub Actions

**Alternatives considered:** Jenkins, CircleCI  
**Reason:** Native GitHub integration, free for public repos, 
and directly relevant since the platform itself uses GitHub 
webhooks. Using the same tool for the platform's CI/CD and 
the platform's webhook feature creates useful symmetry.
