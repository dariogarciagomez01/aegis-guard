## Milestone 1 Objective
Build a high-performance network gateway (API Gateway / Reverse Proxy) capable of intercepting asynchronous chat completion requests while emulating the industry-standard OpenAI API specification. The gateway must natively measure response latency and safely forward payloads to the underlying LLM provider (local or remote) without introducing overhead or blocking the client experience.

### 1. Core Dependencies and Technical Justification
To maintain a lean and production-ready virtual environment, we will install exactly four production dependencies using Poetry. No extra overhead will be introduced.

1. **fastapi**
    - *What it is:* A modern, fast web framework for building APIs with Python.
    - *Why we use it:* A reverse proxy lives and dies by network performance. FastAPI is built on top of Starlette and handles asynchronous programming (async/await) natively. This allows our server to handle thousands of concurrent streaming connections without blocking the main execution thread.

2. **uvicorn**
    - *What it is:* A lightning-fast ASGI (Asynchronous Server Gateway Interface) server implementation.
    - *Why we use it:* Native Python cannot listen for incoming asynchronous HTTP requests on a network port by default. Uvicorn serves as the high-performance engine that runs our FastAPI application.

3. **pydantic**
    - *What it is:* Data validation and settings management using Python type hinting.
    - *Why we use it:* Client applications will send complex JSON payloads (including parameters like temperature, stream flags, and message history arrays). Pydantic will intercept incoming payloads, validate them against the official OpenAI specifications, and raise immediate structure errors before wasting compute resources forwarding malformed requests to the AI.

4. **httpx**
    - *What it is:* A next-generation HTTP client for Python supporting async operations.
    - *Why we use it:* Our proxy acts as a middleman: it intercepts a request, processes metrics, and must then forward (re-route) that request to Ollama or OpenAI. Httpx allows us to fire these outbound requests completely asynchronously. The traditional requests library is synchronous (blocking) and would drastically bottleneck proxy throughput.

### 2. Architectural Design and Pattern Justification
To avoid a monolithic codebase, we reject placing all logic inside a single `main.py` file. Instead, we implement clean architecture principles focusing on Loose Coupling and the Adapter Pattern.

#### The Problem We Avoid: Tight Coupling
Hardcoding the proxy to make direct requests to a single third-party API creates a rigid system. If the engineering team decides to shift to a local model via Ollama or an alternative provider like Anthropic, the entire backend would require a massive, error-prone rewrite.

#### The Solution: The Adapter Pattern
We introduce an abstraction layer between the incoming gateway traffic and the upstream AI infrastructure. The proxy server only communicates with a generic interface, remaining completely agnostic to the specific model running behind the scenes.

- **Step 1: The Interface** (`src/common/providers.py`)
    We define a strict abstract base class (`LLMProvider`) acting as a contract: "Any AI provider integrated into Aegis Guard must expose an asynchronous method named `generate` that accepts a standardized list of messages and returns a structured string response."

- **Step 2: Concrete Adapters**
    We build separate modules for `OllamaProvider` and `OpenAIProvider`. These components isolate vendor-specific API formats, translating our generic internal contract into specific network payloads required by each respective platform.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:
1. **Environment Provisioning:** Run Poetry installation commands to lock down the 4 core dependencies inside `poetry.lock`. (DONE)
2. **Contract Definition:** Write the abstract base class and type schemas for the provider system under `src/common/`. (DONE)
3. **Local Adapter Implementation:** Build the concrete implementation for Ollama to establish connectivity with models running on the local host. (DONE)
4. **The Interception Endpoint:** Program the `POST /v1/chat/completions` route in FastAPI, utilizing Python's native `time` library to calculate exact high-resolution network latency mathematically.