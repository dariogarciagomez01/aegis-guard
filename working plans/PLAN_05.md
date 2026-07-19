# Milestone 5 Objective
Optimize the Aegis Guard gateway by introducing a localized Semantic Cache layer. This milestone aims to drastically reduce Time To First Token (TTFT) and eliminate redundant upstream LLM API costs for semantically equivalent queries. By embedding a serverless vector database and an asynchronous background-writing pipeline, the proxy will intercept client prompts, calculate similarity vectors, and instantly serve cached responses for matching intents without ever hitting the upstream model providers.

### 1. Core Dependencies and Technical Justification
To implement a high-performance semantic cache while preserving Aegis Guard's portable, zero-ops philosophy, we introduce **exactly two** production-ready libraries:

1. **LanceDB**
   - *What it is:* An open-source, serverless, embedded vector database built in Rust, designed to run directly inside the application process (much like SQLite).
   - *Why we use it:* Conventional vector databases (like Qdrant or Milvus) require running separate server daemons, violating our single-container/zero-ops deployment goal. LanceDB stores vectors, metadata, and raw payloads inside a single localized directory. It leverages flat, lightning-fast disk-based operations, allowing us to perform Nearest-Neighbor (KNN) lookups in microsecond ranges with virtually no memory overhead.
2. **FastEmbed (by Qdrant) or Ollama Embeddings API**
   - *What it is:* A highly optimized, lightweight Python library for generating vector embeddings locally using ONNX Runtime, or alternatively, leveraging our running Ollama daemon's `/api/embeddings` endpoint.
   - *Why we use it:* Importing heavy machine learning frameworks like PyTorch or Transformers would bloat Aegis Guard’s footprint by gigabytes and slow down startup times. FastEmbed runs quantized, lightweight models on native CPU with minimal memory, while Ollama's API allows us to offload vectorization entirely to our existing daemon. This ensures our embedding generation pipeline remains blazing fast and container-friendly.

### 2. Architectural Design and Pattern Justification
When introducing semantic caching, we must avoid two critical architectural traps: **Synchronous Bottlenecks** (blocking the client’s HTTP response while writing new embeddings to the database) and **Over-Sensitivity** (failing to match queries because of minor typos or wording changes).

#### The Problem We Avoid: Blocking I/O on Cache Writes and Brittle Key-Value Lookups
Traditional caches (like Redis) perform strict exact-string matching. If a user asks "How do I check tire pressure?" and later "Tell me how to check tire pressure," a traditional cache misses. Semantic caching solves this by comparing the mathematical distance (Cosine Similarity) between query vectors:

$$Cosine\,Similarity = \frac{\mathbf{A} \cdot \mathbf{B}}{\|\mathbf{A}\| \|\mathbf{B}\|}$$

However, calculating an embedding and writing a new prompt-response pair to a database is an expensive I/O operation. If we do this synchronously *before* returning the LLM response to the client, we destroy our latency optimizations. 

- **Step 1: The Fast-Path Check (Vector Search)**
  When a request passes the rate limiter, Aegis Guard converts the incoming prompt into a vector. It queries the local LanceDB instance for the single nearest neighbor. If the similarity score is above our configurable threshold (e.g., $\ge 0.88$), we have a **Cache Hit**. The proxy short-circuits, bypasses the LLM entirely, and returns the cached answer instantly.
- **Step 2: The Non-Blocking Async Write (FastAPI BackgroundTasks)**
  If the query is a **Cache Miss**, the proxy forwards the request to the LLM as usual. However, once the LLM finishes generating the response (or the stream closes), we dispatch the vectorization and database insertion of this new QA pair to a FastAPI `BackgroundTask`. The client receives their tokens immediately, while the cache is updated silently in the background.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task 5.1: serverless vector database integration and schema modeling**
   Installs and configures LanceDB to persist data under `src/database/vector_store`, and defines the schema to store query vectors, raw prompts, model responses, and model metadata. (DONE)
2. **task 5.2: vectorization middleware component**
   Implements an asynchronous utility class to handle embedding generation (using Ollama's embedding API or FastEmbed) with robust error boundaries. (DONE)
3. **task 5.3: semantic lookup and mathematical similarity evaluation**
   Develops the core search logic using Cosine Similarity metrics, exposing a configurable similarity threshold parameter via environment variables (`SEMANTIC_CACHE_THRESHOLD`). (DONE)
4. **task 5.4: non-blocking background caching and telemetry integration**
   Connects the cache engine to `/v1/chat/completions`. Leverages FastAPI's `BackgroundTasks` to write new cache entries asynchronously, and injects custom telemetry metadata for hit tracking:
   ```json
   "_aegis_guard_meta": {
       "latency_ms": 1.84,
       "provider": "semantic_cache",
       "status": "cached_hit",
       "similarity_score": 0.94
   } (DONE)