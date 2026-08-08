# Aegis Guard Gateway — Deployment & Initialization Guide

This document outlines the end-to-end procedures required to initialize, containerize, and deploy the **Aegis Guard** LLM Reverse Proxy alongside its local LLM dependency (Ollama) in production and development environments.

---

## 📋 Prerequisites

Ensure the following runtimes and services are installed on the host system:

*   **Docker Desktop** (v24.0+ recommended) & **Docker Compose**
*   **Ollama** (Local LLM Daemon)
*   **Python 3.11+** with **Poetry** (used for database seeding and local development workflows)

---

## 🚀 End-to-End Deployment Workflow

### Step 1: Start & Configure Ollama Daemon
Aegis Guard routes live LLM requests and fallback operations to local LLM instances. You must start the Ollama daemon and pull the target model before launching the proxy gateway.

1. Launch Ollama in your terminal or background service:
```bash
ollama serve
```

2. Pull the default local model required by Aegis Guard:

```bash
ollama pull llama3
```

3. Verify that Ollama is responding on port `11434`:

```bash
curl http://localhost:11434/api/tags
```

---

### Step 2: Environment Configuration

Copy the environment variable template to create your active `.env` file:

```bash
cp .env.example .env
```

Ensure your `.env` contains the correct network reference for Ollama. When running Aegis Guard inside Docker Desktop, use `host.docker.internal` so the container can reach the host network:

```env
SEMANTIC_CACHE_THRESHOLD=0.88
OLLAMA_BASE_URL=[http://host.docker.internal:11434](http://host.docker.internal:11434)
```

---

### Step 3: Database & API Key Initialization (Seeding)

Before launching the container for the first time, run the seed script to create the SQLite schema (`aegis_guard.db`) and generate the initial client API keys:

```bash
poetry run python seed.py
```

*Note down the Bearer API Key generated in the terminal output; you will use it to authenticate incoming requests.*

---

### Step 4: Container Orchestration (Docker Compose)

Build the multi-stage Docker image and launch the gateway container in detached mode:

```bash
docker compose up --build -d
```

To monitor real-time structured JSON logs emitted by the gateway:

```bash
docker compose logs -f aegis-guard
```

---

## 🩺 System Verification & Health Checks

### 1. Gateway Status Check

Verify that the FastAPI event loop inside Docker is live:

```bash
curl -X GET http://localhost:8000/health
```

**Expected Response:**

```json
{
  "status": "healthy",
  "service": "aegis-guard-proxy"
}
```

### 2. End-to-End Pipeline Ingress Test

Issue a standard OpenAI-compliant `/v1/chat/completions` request using your seeded API key:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_GENERATED_API_KEY" \
  -d '{
    "model": "llama3",
    "messages": [{"role": "user", "content": "What is semantic caching?"}],
    "stream": false
  }'
```

---

## 💾 State Persistence & Volume Management

Aegis Guard operates stateless application processes inside the Docker container while persisting critical state on the host file system via volume mounts:

* `./aegis_guard.db` -> `/app/aegis_guard.db`: Persists user credentials, rate-limiting tiers, and audit trails.
* `./src/database/vector_store` -> `/app/src/database/vector_store`: Persists LanceDB vector tables for instantaneous cold-start semantic cache hits across container restarts.

To stop the services while preserving all state:

```bash
docker compose down
```