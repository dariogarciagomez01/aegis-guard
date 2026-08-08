# Milestone 6 Objective
Finalize the Aegis Guard gateway by implementing comprehensive observability (JSON-structured logging and audit trails), immutable containerization via Docker, and rigorous load-testing validation. This milestone transitions the proxy from a local development script into a production-ready, deployable artifact capable of proving its performance optimizations (Rate Limiting and Semantic Caching) under simulated high-concurrency traffic.

### 1. Core Dependencies and Technical Justification
To package the gateway and validate its resilience under pressure, we introduce the following industry-standard tools:

1. **Docker (Multi-Stage Builds)**
   - *What it is:* A containerization platform that packages the application, its environment, and dependencies into a single, portable image.
   - *Why we use it:* To eliminate the "it works on my machine" anti-pattern. By using multi-stage builds, we compile dependencies in a heavy image and transfer only the compiled binaries to a lightweight runtime image, minimizing the final footprint and reducing attack surfaces.
2. **Locust**
   - *What it is:* An open-source, Python-based load testing tool capable of generating millions of concurrent requests from a single machine.
   - *Why we use it:* Traditional testing proves functionality; load testing proves architecture. Locust will simulate hundreds of concurrent users attacking the `/v1/chat/completions` endpoint, allowing us to empirically validate that our asynchronous `asyncio.Lock` rate limiter blocks excess traffic (HTTP 429) without crashing the event loop, and that our LanceDB semantic cache maintains millisecond latencies under heavy load.
3. **Python Standard `logging` (Structured JSON)**
   - *What it is:* A native module adapted to output logs as structured JSON objects rather than plain text strings.
   - *Why we use it:* Plain text `print()` statements are useless in production. Structured JSON logs allow external log aggregators (like Datadog, Loki, or ELK) to parse, filter, and alert on specific metadata fields (e.g., latency, provider, cache hits) instantly.

### 2. Architectural Design and Pattern Justification
When moving to production, an API gateway must be completely transparent about its internal state and impenetrable against traffic spikes. We must avoid **Silent Failures** and **Resource Exhaustion**.

#### The Problem We Avoid: The Black Box and The Thundering Herd
If a client complains about a rejected API key or a slow response, an unmonitored proxy provides no diagnostic evidence. Furthermore, if a sudden spike of traffic hits the gateway, an unoptimized application will consume all available RAM and crash. 

- **Step 1: Immutable Artifacts and Environment Isolation**
  Aegis Guard will be containerized. The `Dockerfile` will install Poetry, export the exact deterministic dependency tree, and run the FastAPI application on an exposed port (8000). The local SQLite and LanceDB databases will be mounted as external volumes to ensure data persistence across container restarts.
- **Step 2: Audit Trails and Structured Telemetry**
  We replace terminal prints with a centralized logger. Every incoming request generates a single, comprehensive JSON log entry containing the timestamp, client IP, target model, HTTP status code, and resolution time. Security events (like unauthorized access or rate-limit breaches) are logged as warnings or errors.
- **Step 3: The Stress Test Validation (Load Shedding)**
  We write a Locust script (`locustfile.py`) defining a virtual user behavior. The test will swarm the proxy with hundreds of parallel requests. We expect the architecture to gracefully degrade: allowing allowed traffic through the fast-path (Cache) or slow-path (Ollama), while instantly shedding excess requests with HTTP 429 responses, keeping CPU and Memory usage perfectly stable.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task 6.1: structured logging and central audit trail**
   Implements a custom JSON formatter for the Python `logging` module. Replaces all existing `print()` statements in `main.py` and middleware with structured logger calls containing Aegis Guard metadata.
2. **task 6.2: dockerization and production deployment setup**
   Writes a highly optimized, multi-stage `Dockerfile` and a `docker-compose.yml` file to orchestrate the proxy container, exposing necessary ports and mapping persistent database volumes for SQLite and LanceDB.
3. **task 6.3: locust load testing and performance benchmarking**
   Develops `tests/locustfile.py` to simulate concurrent API traffic. Executes the stress test against the running Docker container to empirically validate the resilience of the sliding-window rate limiter and the semantic cache latency.