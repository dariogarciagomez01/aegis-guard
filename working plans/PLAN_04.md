# Milestone 4 Objective
Secure the Aegis Guard reverse proxy infrastructure by transforming it into a multi-tenant gateway. This milestone introduces a secure API key authentication system and a localized traffic-shaping engine (Rate Limiting). These components will validate client credentials, monitor usage bounds, and perform graceful load shedding to protect upstream cloud budgets and prevent resource exhaustion on the local Ollama daemon.

### 1. Core Dependencies and Technical Justification
To introduce database persistence and traffic management while preserving our ultra-lightweight, high-performance architecture, we introduce **exactly one** production dependency:

1. **SQLModel (with Native SQLite)**
   - *What it is:* A library built on top of SQLAlchemy and Pydantic designed for seamless database interaction inside FastAPI applications.
   - *Why we use it:* Because Aegis Guard already relies on Pydantic for request parsing and validation, SQLModel eliminates architectural redundancy by allowing our database tables to double as Pydantic schemas. SQLite is selected as the storage engine because it is embedded natively in the Python standard library, requires zero external server overhead (unlike PostgreSQL or Redis), keeps local development highly portable, and handles concurrent read operations via WAL (Write-Ahead Logging) mode with sub-millisecond latencies.
2. **Native Thread-Safe In-Memory Stores**
   - *What it is:* Python’s built-in `collections.defaultdict` coupled with `asyncio.Lock` mechanisms.
   - *Why we use it:* Rather than forcing the installation of an external caching tier like Redis—which breaks our zero-ops local student deployment goal—we will implement a high-performance, fixed-window or token-bucket rate limiter directly in the runtime application memory. This ensures that throttle verification adds negligible CPU overhead to the proxy pipeline.

### 2. Architectural Design and Pattern Justification
As Aegis Guard evolves into a multi-tenant gateway, we must prevent two systemic flaws: database query bottlenecks on every incoming text chunk and catastrophic resource depletion from rogue client loops.

#### The Problem We Avoid: Unauthenticated Access, Database Thrashing, and Financial Credit Draining
Allowing public access to cloud endpoints invites denial-of-service vectors that can instantly deplete OpenAI API credits. However, executing a slow, blocking database query to check a user's API key for every single streaming token would degrade our newly optimized TTFT metrics. We solve this by decoupling authentication verification from token streaming and isolating traffic control at the gateway entry point.

- **Step 1: Relational Multi-Tenant Data Schema** (`src/database/models.py` & `connection.py`)
  We establish an explicit relational layout tracking `User` entities, active `ApiKey` models, and custom `RateLimitConfig` profiles. Raw API tokens are indexed heavily within SQLite to guarantee $O(1)$ lookups during the handshake phase.
- **Step 2: FastAPI Dependency Injection Gatekeeper** (`src/proxy/auth.py`)
  We leverage FastAPI’s native `Security` and `Depends` patterns to build an authentication interceptor. This structural pattern isolates security logic from business routing, extracting the `Authorization: Bearer <key>` header and verifying its status *before* the request ever triggers the provider factory.
- **Step 3: Traffic Control and Load Shedding** (`src/proxy/limiter.py`)
  Before routing traffic upstream, an in-memory sliding window or token-bucket algorithm evaluates the rate metrics mapped to the client's API key. If a user breaches their designated Requests Per Minute (RPM) quota, the proxy sheds the load immediately, returning a standard error response and completely bypassing the LLM execution layer.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task 4.1: database integration and multi-tenant schema modeling** 
   Configures the SQLModel storage engine, initializes the local SQLite database context manager, and defines the structural schemas for users, keys, and quotas. (DONE)
2. **task 4.2: extraction and validation authentication dependency**
   Builds the secure HTTP Bearer token extractor as a FastAPI dependency component, locking down the `/v1/chat/completions` endpoint against unauthenticated traffic. (DONE)
3. **task 4.3: localized high-performance rate limiting engine**
   Architects a non-blocking, thread-safe in-memory sliding window tracking system to record request intervals per authenticated API key. (DONE)
4. **task 4.4: standard-compliant load shedding and error mapping**
   Integrates explicit exception handlers to intercept failures, returning standardized HTTP 401 (Unauthorized) and HTTP 429 (Too Many Requests) JSON payloads matching global upstream standards. (DONE)