# Milestone 2 Objective
Evolve the reverse proxy into a hybrid, multi-provider gateway capable of dynamically routing incoming traffic between local infrastructure (Ollama) and cloud infrastructure (OpenAI) based on the clients's requested model. The architecture must enforce strict isolation of sensitive API credentials utilizing production-grade enviroment variables, and decouple instantiation logic from the API layers by implementing the Factory Design to gurantee compliance with SOLID principles.

### 1. Core Dependencies and Technical Justification
To expand our gateway capabilities without degrading performance or introducing security vulnerabilities, we introduce exactly one new production dependency via Poetry:
1. **pydantic-settings**
    - *What it is:* A dedicated settings management library built on top of Pydantic that automatically loads configuration from environment variables and `.env` files.
    - *Why we use it:* Hardcoding secret API keys or service URLs within the repository is a critical security risk and violates the "12-Factor App" methodology. `pydantic-settings` provides strict type hints and validation for configuration. The proxy server will fail immediately at startup if a required variable (like`OPENAI_API_KEY`) is missing or malformed, protecting out system early.

### 2. Architecturak Design and Pattern Justification
As we scale to multiple AI providers, we must prevent code smell and tight coupling wihin out FastAPI route controllers. We implement the Factory Desgin Patterns to enforce the Open/Close Principle (SOLID).

#### The Problem We Avoid: Tight Coupling and Conditional Bloat
Without a Factory, the `main.py` route controller would have to evaluate the model string using complex `if/else` ot `match/case` blocks to manually instantiate `OllamaProvider` or `OpenAIProvider`. Every time a new model or third-party vendor is introduced, the core routing logic would require modifications, exposing production features to unexpected bugs.

- **Step 1: Configuration Shield** (`src/common/config.py`)
    We define a global configuration object that reads validated keys from the local `.env` environment, securing all remote handshakes.
- **Step 2: Concrete Cloud Adapter** (`src/common/openai_provider.py`)
    We build the `OpenAIProvider` inheriting from our pre-existing `BaseProvider` contract, isolating its distinct payload payload structure and token authentication requirements.
- **Step 3: The Dynamic Fabricator** (`src/common/factory.py`)
    We implement the centralized `ProviderFactory`. It evaluates the incoming string (e.g., `gpt-4o` vs `llama3`), constructs the chosen adapter injects the proper configuration, and returns the unified `BaseProvider` interface.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task 2.1: environment configuration and pydantic-settings setup**
    Provisions `pydantic-settings` into the virtual environment, defines the environment schema in `src/common/config.py`, and secures credentials using `.env` validation. (DONE)
2. **task 2.2: async openai provider implementation**
    Develops the concrete cloud adapter utilizing `httpx.AsyncClient` to establish high-performance asynchronous connections to the official OpenAI endpoints. (DONE)
3. **task 2.3: dynamic provider factory pattern implementation**
    Builds the central factory module to encapsulate instantiation, and refactors `src/proxy/main.py` to route traffic dynamically using the unified abstraction. (DONE)
4. **task 2.4: cross-routing integration testing and multi-model benchmarking**
    Executes end-to-end integration tests using the interactive `/docs` UI to verify seamless routing across local and remote engines while capturing comparative latency metrics. (DONE)
