---
paths:
  - "**/*.py"
---

# Python conventions

No formatter or linter is configured, so match the surrounding code.

- **Python version**: the Docker image runs Python 3.11 (`python:3.11-slim`); the local `.venv` is 3.14. Write code that runs on 3.11.
  - The post-edit hook compiles with the venv and also parses with `feature_version=(3, 11)`, which rejects `type` statements and `def f[T]`.
  - 3.12-style f-strings that reuse the outer quote still pass the check.
- **Imports**: absolute from the repo root with the `src.` prefix, e.g. `from src.common.providers import BaseProvider, ChatMessage`. No relative imports; `src/` and `tests/` have no `__init__.py`.
- **Typing**: use `typing` generics (`List[...]`, `Optional[...]`, `AsyncGenerator[str, None]`, `Any`), not `list[...]`.
  - Annotate parameters and return types on new or changed public functions, as the adapters, factory, limiter and auth already do.
  - Many older functions in `main.py`, `connection.py`, `vector_db.py` and `logger.py` lack return types; don't add them to lines you aren't changing.
- **Docstrings**: triple double quotes with a short paragraph. Public contracts use `:param x:` / `:return:` fields (see `src/common/providers.py`, `src/common/factory.py`). Small helpers get one-line docstrings.
- **Comments**: full English sentences. Number the phases of longer functions with `# Step N: ...`. Separate sections of long modules with uppercase `# --- SECTION NAME ---` banners.
- **Logging**: `from src.utils.logger import logger`, then `logger.info("Sentence-case message", extra={"extra_data": {"snake_case_key": value}})`.
  - Pass errors as `{"error": str(e)}`, and round `latency_ms` to 2 decimals.
  - Use `warning` for rate limits and when a request continues on a degraded path ("Primary engine disrupted", cache bypass), and `error` for failures. The middleware already logs every status ≥ 400 except 429 at `error`, and unhandled exceptions at `critical`.
  - No `print()` in `src/`; only the scripts (`seed.py`, `tests/`) print.
- **Errors**:
  - Adapters (`*_provider.py`, `src/proxy/embeddings.py`) raise `RuntimeError("<vendor-specific message>")` for upstream and connection failures. `embeddings.py` also raises `ValueError` when the reply has no vector.
  - Before a response starts, `chat_completions` maps `RuntimeError` to HTTP 502 and anything else to 500. After an SSE stream starts, failures go in-band as `data: {"error": "..."}`, then the stop chunk and `data: [DONE]`.
  - Error bodies use FastAPI's `{"detail": ...}` envelope: auth failures are 401 with a string `detail`, and rate limits are 429 with `{"detail": {"error": {"message", "type", "param", "code"}}}`.
- **Responses**: keep the OpenAI shapes.
  - `chat.completion` for JSON. For streams, `chat.completion.chunk` events sent as `data: {json}\n\n`, a stop chunk, then `data: [DONE]\n\n`.
  - Aegis Guard metadata goes in the extra `_aegis_guard_meta` object.
  - IDs are `chatcmpl-<16 hex>`, or `chatcmpl-cache-<16 hex>` for cache hits.
- **Async**:
  - Each outbound call opens its own `async with httpx.AsyncClient(...)`. LLM calls get a 30 s timeout (on the client in `openai_provider.py`, per request in `ollama_provider.py`); embeddings use `timeout=10.0, trust_env=False`.
  - The auth lookup and the cache search run in `await asyncio.to_thread(...)`. `save_to_cache` runs inline in the `cache_response_background` task. Put new blocking calls (SQLModel, LanceDB) in `asyncio.to_thread`.
  - Cache writes are scheduled with FastAPI `BackgroundTasks`.
- **Singletons**: module-level `settings` (config.py), `limiter`, `logger` and `engine`. In `vector_db.py`, `get_vector_db()` creates `_db_client` lazily, and `init_vector_db(768)` (called from the lifespan hook) opens or creates `_cache_table`. `get_cache_table()` raises before that.
- **Naming**:
  - Adapters are `<Vendor>Provider` in `src/common/<vendor>_provider.py`. They subclass `BaseProvider`, return plain text from `generate()` and yield text tokens from `generate_stream()`, and are routed by `ProviderFactory`.
  - SSE generators end in `_generator`. Constants are `UPPER_SNAKE`. Prometheus metrics start with `aegis_guard_`.
- **Formatting**: 4-space indents, double quotes, f-strings. Many files have whitespace-only blank lines and no final newline; don't reformat lines you aren't changing.
