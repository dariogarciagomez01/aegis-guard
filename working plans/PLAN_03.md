# Milestone 3 Objective
Upgrade Aegis Guard to support reactive, real-time token transmission via asynchronous streaming (`text/event-stream`), drastically optimizing the Time To First Token (TTFT) for consuming applications. Simultaneously, architect an active resilience engine within the proxy layer capable of intercepting cloud infrastructure dropouts (timeouts, rate limits, or API errors) and executing an instantaneous, silent fallback to local models (Ollama), achieving a zero-downtime high-availability gateway.

### 1. Core Dependencies and Technical Justification
To maintain a hyper-lightweight footprint and prevent dependency bloating, we introduce **exactly zero new production dependencies** via Poetry. 
1. **Native Python & FastAPI Asynchronous Core**
    - *What it is:* Built-in capabilities of Python's standard library (`typing.AsyncGenerator`, `async/await`) combined with FastAPI's native `StreamingResponse`.
    - *Why we use it:* FastAPI is built directly on top of Starlette and Uvicorn, meaning it natively supports Asynchronous Server Gateway Interface (ASGI) streaming protocols like Server-Sent Events (SSE). Introducing external SSE libraries would add dead weight. By leveraging native async generators, we stream token chunks over an open HTTP connection with negligible memory overhead, ensuring the proxy remains highly performant under heavy traffic.

### 2. Architectural Design and Pattern Justification
As we move into reactive data streams, we face two critical architectural problems: blocking network pipes and cascading single-point-of-failure liabilities. 

#### The Problem We Avoid: Tight Coupling, Head-of-Line Latency, and Total Service Blackouts
Without streaming, the client must wait for the remote LLM to generate its entire response (sometimes taking up to 5–10 seconds) before receiving a single word, degrading the user experience. Furthermore, if OpenAI hits a rate limit (HTTP 429) or suffers an outage, the client application crashes immediately. 

We solve this by wrapping our dynamic factory execution in a resilient, asynchronous stream interceptor.

- **Step 1: Asynchronous Stream Contract Extension** (`src/common/providers.py`)
    We define an immutable abstract contract `generate_stream` returning an `AsyncGenerator`. This forces all present and future concrete adapters to yield raw string tokens sequentially as they arrive from the network buffer.
- **Step 2: Reactive Upstream Adaptation** (`src/common/ollama_provider.py` & `src/common/openai_provider.py`)
    We refactor our concrete adapters to consume chunks natively. `OllamaProvider` utilizes its local stream engine, while `OpenAIProvider` leverages `httpx.AsyncClient` to read stream bytes line-by-line without blocking the main event loop.
- **Step 3: The Active Fallback Interceptor** (`src/proxy/main.py` or routing layer)
    We implement a structural exception-handling wrapper around the stream initialization. If the primary cloud provider raises a connection, timeout, or authentication exception, the proxy catches the error silently, instantly boots up the local `OllamaProvider`, and redirects the token stream in milliseconds.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task 3.1: provider contract extension for asynchronous generation**
    Integrates `AsyncGenerator` type configurations into `src/common/providers.py` and establishes the strict abstract interface for real-time token yielding. (DONE)
2. **task 3.2: reactive stream processing in upstream adapters**
    Upgrades both `OllamaProvider` and `OpenAIProvider` to consume upstream streams, translating vendor-specific multi-part payloads into clean, isolated text chunks. (DONE)
3. **task 3.3: fastapi event-stream endpoint implementation**
    Exposes the streaming capabilities to the outer HTTP layer by integrating FastAPI's `StreamingResponse` configured with a `text/event-stream` media type. (DONE)
4. **task 3.4: active fault-tolerant fallback engine**
    Builds the resilience layer that traps upstream cloud disruptions and triggers an immediate, seamless hot-swap to the local infrastructure daemon. (DONE)
5. **task 3.5: high-resolution streaming telemetry and failover profiling**
    Instruments the streaming controller to calculate Time To First Token (TTFT) and injects custom performance headers indicating whether a fallback execution occurred. (DONE)