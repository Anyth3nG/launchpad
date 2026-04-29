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
