# Aegis Guard

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![LanceDB](https://img.shields.io/badge/Vector_DB-LanceDB-orange)](https://lancedb.com/)
[![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Aegis Guard** is a high-performance AI Gateway / Proxy compatible with the OpenAI API specification (`/v1/chat/completions`), built to orchestrate, secure, and observe local Large Language Model (LLM) inference running on **Ollama**.

It provides a production-ready middleware layer featuring API Key authentication, **dynamic rate limiting per client**, **vector semantic caching**, and structured logging for complete observability.

---

## 📐 System Architecture & Flow

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client / Postman / Locust
    participant Proxy as Aegis Guard Gateway (FastAPI)
    participant DB as SQLite (Auth & Limits)
    participant Cache as Semantic Cache (LanceDB)
    participant LLM as Ollama / Cloud LLM

    Client->>Proxy: POST /v1/chat/completions (Bearer Key)
    Proxy->>DB: Validate API Key & Check Sliding Rate Limit (RPM)
    
    alt Rate Limit Exceeded
        DB-->>Proxy: Quota Exhausted
        Proxy-->>Client: HTTP 429 Too Many Requests (under 10ms)
    else Quota Allowed
        Proxy->>Cache: Check Semantic Vector Cache (Cosine Sim >= 0.88)
        alt Cache Hit
            Cache-->>Proxy: Return Cached Vector Response
            Proxy-->>Client: HTTP 200 OK (Cached Static / SSE Stream)
        else Cache Miss / Disabled
            Proxy->>LLM: Forward Request (Ollama / Cloud Provider)
            alt Primary Cloud Provider Down
                LLM-->>Proxy: Connection Failure
                Proxy->>LLM: Silent Hot-Swap Fallback (Local Llama 3)
            end
            LLM-->>Proxy: Stream Tokens / Complete Payload
            Proxy-->>Client: HTTP 200 OK (SSE Stream / JSON Response)
            Proxy--)Cache: Background Task: Store Embedding in LanceDB
        end
    end
```

---

## 🚀 Key Features

* **OpenAI API Compatibility:** Exposes standard `/v1/chat/completions` endpoints that integrate seamlessly with official SDKs, Postman, or agent frameworks (LangChain, LlamaIndex).
* **API Key Rate Limiting:** Granular quota control (RPM - *Requests Per Minute*) backed by SQLite and evaluated on every incoming request with rejection latencies of $<10\text{ ms}$.
* **Vector Semantic Cache:** Cuts latency and inference compute by short-circuiting re-evaluations through **LanceDB** vector storage and similarity indexing (can be toggled off for raw benchmark testing).
* **Observability & Metrics:** Native **Prometheus** metrics export (`/metrics`) alongside high-throughput structured JSON logging.
* **Resilience & Fallback:** Handles network drops gracefully and provides clear error mapping (`502 Bad Gateway`) for Ollama daemon connection issues.
* **Containerized Deployment:** Fully reproducible setup using **Docker Compose**, pre-configured for host-to-container communication across macOS, Linux, and Cloud environments.
* **Integrated Load Testing:** Automated benchmarking suite with **Locust** to evaluate concurrency and stress limits.

---

## 🛠️ Tech Stack

| Component | Technology |
| --- | --- |
| **Web Framework** | FastAPI (Uvicorn / ASGI) |
| **Dependency Manager** | Poetry |
| **LLM Inference Engines** | Ollama (`llama3:8b`), OpenAI API |
| **Relational Database** | SQLite (SQLModel / SQLAlchemy) |
| **Vector DB & Caching** | LanceDB (PyArrow vector indexing) |
| **Observability & Metrics** | Prometheus (`prometheus-client`), Structured JSON Logging |
| **Async HTTP Client** | HTTPX |
| **Validation & Settings** | Pydantic v2 / Pydantic Settings |
| **Containerization** | Docker / Docker Compose |
| **Load Testing** | Locust |

---

## 📁 Project Structure

```text
aegis-guard/
├── .env.example                # Environment variable template
├── docker-compose.yml          # Container stack configuration
├── Dockerfile                  # Multi-stage container build file
├── locustfile.py               # Distributed load testing suite
├── pyproject.toml              # Dependencies & project metadata
├── seed.py                     # Database initialization & tenant provisioning
├── docs/
│   ├── assets/                 # Architecture diagrams & benchmark assets
│   ├── diagrams/               # Architecture, sequence & class diagrams
│   ├── working plans/          # Milestone plans and feature specifications
│   └── DEPLOYMENT.md           # Production deployment & execution guide
├── src/
│   ├── common/
│   │   ├── config.py           # Centralized application settings (Pydantic BaseSettings)
│   │   ├── factory.py          # Provider Factory (Open/Closed design)
│   │   ├── ollama_provider.py  # Local inference driver
│   │   ├── openai_provider.py  # Cloud inference driver with fallback support
│   │   └── providers.py        # Abstract Base Class contract & message schemas
│   ├── database/
│   │   ├── connection.py       # Engine creation & session lifecycle
│   │   ├── models.py           # SQLModel schemas (User, ApiKey)
│   │   └── vector_db.py        # LanceDB connection, indexing & vector queries
│   ├── proxy/
│   │   ├── auth.py             # Bearer authentication & tenant validation dependency
│   │   ├── embeddings.py       # Vector embedding engine
│   │   ├── limiter.py          # Thread-safe in-memory sliding-window limiter
│   │   └── main.py             # API Router, SSE generators, metrics & middleware
│   └── utils/
│       └── logger.py           # High-throughput structured JSON logging
└── tests/
    └── test_ollama_embed.py    # Embedding engine unit tests
```

---

## ⚙️ Configuration & Environment Variables

Create a `.env` file in the root directory based on the following template:

```env
# Gateway Configuration
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Vector similarity threshold (0.0 to 1.0)
SEMANTIC_CACHE_THRESHOLD=0.88

# Disable cache to measure raw LLM latency
DISABLE_SEMANTIC_CACHE=true

```

---

## 🚀 Local Setup & Deployment Guide

### 1. Prerequisites

* **Docker Desktop** installed and running.
* **Ollama** installed locally with the `llama3` model pulled:
```bash
ollama pull llama3

```



---

### 2. Start Ollama Server (macOS)

To allow the Docker container to communicate with Ollama running on the macOS host, start Ollama bound to all network interfaces (`0.0.0.0`):

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve

```

---

### 3. Seed Database & Generate API Key

In a second terminal, initialize the database and create a user with an associated API Key:

```bash
# Optional: Remove legacy database file
rm -f aegis_guard.db

# Run database seed
poetry run python seed.py

```

> ⚠️ **Note:** Copy the generated API Key printed to the console (formatted as `ag_live_...` or `ak_live_...`).

---

### 4. Launch the Proxy in Docker

Build and run the **Aegis Guard** container:

```bash
docker compose up --build -d

```

Verify container health by inspecting logs:

```bash
docker compose logs -f aegis-guard

```

The gateway server will be live at `http://localhost:8000`. Interactive API documentation is available at `http://localhost:8000/docs`.

---

## 🧪 API Usage Example

Chat Completion request (`POST /v1/chat/completions`):

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY_HERE" \
  -d '{
    "model": "llama3",
    "messages": [
      {"role": "user", "content": "Explain briefly what an API Gateway is."}
    ],
    "stream": false
  }'

```

---

## 📊 Load Testing & Performance Benchmark

Aegis Guard was subjected to concurrency stress testing using **Locust** running 10 virtual users sending continuous requests to `/v1/chat/completions`.

![Locust Benchmark Charts](docs/assets/locust_benchmark.png)

### Telemetry & Chart Analysis

1. **Throughput & Protection (Top Chart):**
   * The gateway sustained a total throughput of **~5.0 req/s**.
   * Red metrics (*Failures/s*) represent intentional **HTTP `429 Too Many Requests`** rejections triggered by the Rate Limiter to shield the local LLM backend from exhaustion.

2. **Latency Breakdown (Middle Chart):**
   * **Inference Overhead:** Uncached live model execution averages ~4.6s–8.0s (P95) on the local `llama3:8b` engine.
   * **Rate Limiter Overhead:** Rate-limited requests are short-circuited and rejected in **<10 ms** (median).

3. **System Stability (Bottom Chart):**
   * Zero unhandled process crashes (`500`/`502`) recorded across peak concurrency bursts with 10 continuous virtual users.

---

## 💡 Performance Takeaways

1. **Protection Efficiency:** The Rate Limiter blocks unauthorized/over-quota requests in $<10\text{ ms}$, shielding Ollama inference workers from resource exhaustion.
2. **Infrastructure Stability:** The FastAPI container handled high-concurrency bursts without connection leaks or elevated failure rates.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).