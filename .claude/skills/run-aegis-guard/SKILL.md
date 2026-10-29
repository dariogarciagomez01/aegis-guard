---
name: run-aegis-guard
description: Build, run, and drive the Aegis Guard gateway. Use when asked to start the proxy, run it locally or in Docker, smoke-test it, call its endpoints, or confirm a change works in the running app.
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/smoke.sh *)
  - Bash("${CLAUDE_SKILL_DIR}/smoke.sh" *)
  - Bash(poetry run python seed.py)
  - Bash(poetry run uvicorn src.proxy.main:app *)
---

Aegis Guard is a FastAPI server exposing an OpenAI-compatible `POST /v1/chat/completions`. Drive it with `${CLAUDE_SKILL_DIR}/smoke.sh`, which:

1. Launches the server in the background if it isn't running.
2. Checks it with `curl`.
3. Stops it again.

Run everything from the repo root, and give the Bash call a 300000 ms timeout.

## Prerequisites

- Poetry 2.x and the in-project virtualenv `.venv`, created by `poetry install`.
- For chat completions: Ollama on `:11434` with `llama3` pulled. For the semantic cache: `nomic-embed-text` too.
  - The server starts without either, and `/health`, `/metrics` and the auth checks work without them.
  - Check the status with `curl -s http://localhost:11434/api/tags`. On macOS, `ollama list` launches the app.
  - If Ollama is down or a model is missing, ask the user. Don't start it or pull models yourself.
- For the Docker path: Docker Desktop running.

## Setup

```bash
poetry install              # once; installs dependencies only (package-mode = false)
poetry run python seed.py   # idempotent; creates ./aegis_guard.db with user dario_dev, key ak_live_dario123456789 (5 RPM)
```

Configuration:

- `.env`, copied from `.env.example`, provides `OLLAMA_BASE_URL` and `OPENAI_API_KEY`. Claude's file tools are denied `.env`, so ask the user when a value matters.
- `DISABLE_SEMANTIC_CACHE` and `DATABASE_URL` come only from the process environment. To run with the cache off, use `smoke.sh --no-cache`.

## Run (agent path)

```bash
${CLAUDE_SKILL_DIR}/smoke.sh                # port 8000; stops the server it started when done
${CLAUDE_SKILL_DIR}/smoke.sh --port 8010    # another port
${CLAUDE_SKILL_DIR}/smoke.sh --keep         # leave the server running afterwards
${CLAUDE_SKILL_DIR}/smoke.sh --no-cache     # start the server with the semantic cache off, so completions reach the LLM
${CLAUDE_SKILL_DIR}/smoke.sh --ollama-url http://localhost:11434   # override .env's OLLAMA_BASE_URL for the server it starts
${CLAUDE_SKILL_DIR}/smoke.sh --stop         # stop a server started with --keep (add --port N if you used one)
```

In later turns, the same script is at `.claude/skills/run-aegis-guard/smoke.sh` relative to the repo root.

What the script does:

- **Launch**: if nothing listens on the port, it starts `poetry run uvicorn src.proxy.main:app` from the repo root, logging to `$TMPDIR/aegis-guard-smoke-<port>.log`. If a server is already listening (a local uvicorn or the Docker container), it tests that one and leaves it running.
- **Basic checks**: `GET /health`, `GET /metrics`, and that requests without a key and with an invalid key get 401.
- **Completions**: when Ollama answers and lists the model, it sends one JSON and one streaming completion with the seeded key. It prints the provider and status: `ollama`, or `semantic_cache` on a cache hit, in which case the LLM wasn't called. Both requests count against the key's 5 RPM.
- **`--stop`**: stops only a gateway that smoke.sh started. Docker and other listeners keep running.
- **Exit code**: 0 when every check that ran passed.

How to use it:

- **When the user asks to start or run the app**: use `--keep`, then give them `http://localhost:8000/docs` and the `--stop` command. When you're only verifying a change, use the default.
- **Report what actually ran**: if the completions were skipped, say the gateway is up but no completion was tested. To force the LLM path, use `--no-cache`.
- **To exercise a specific change**: start with `--keep`, then call the route the diff touches:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ak_live_dario123456789" \
  -d '{"model": "llama3", "messages": [{"role": "user", "content": "Hello"}], "stream": true}'
```

The server log mixes uvicorn's plain-text startup and access lines with the app's JSON lines. The JSON lines are one per request (except `/metrics`), plus `TTFT measured`, cache, fallback and provider-error events. Filter with `grep '^{'` before parsing.

## Run (human path)

```bash
poetry run uvicorn src.proxy.main:app --reload --port 8000   # Swagger UI at http://localhost:8000/docs; Ctrl+C stops it
```

Docker, as in README.md §2–4 (docs/DEPLOYMENT.md has the same steps but starts Ollama with plain `ollama serve`):

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve   # reachable from containers; .env needs OLLAMA_BASE_URL=http://host.docker.internal:11434
docker compose up --build -d             # service aegis-guard, container aegis-guard-proxy, port 8000
docker compose logs -f aegis-guard       # follows forever; agents use --tail 100 instead of -f
docker compose down
```

`smoke.sh` also works against the container: it sees port 8000 in use and tests it as-is.

## Test

```bash
poetry run python -m tests.test_ollama_embed   # manual embeddings check (needs nomic-embed-text); prints ✅/❌, always exits 0
TEST_API_KEY=ak_live_dario123456789 poetry run locust -f locustfile.py --headless -u 10 -r 2 -t 1m --host http://localhost:8000
```

There is no automated test suite yet. `poetry run pytest` collects the manual script above and reports it as failed, because it's an unmarked `async def` and pytest-asyncio isn't installed.

## Gotchas

- **`OLLAMA_BASE_URL` on local runs**: `.env.example` ships the Docker value `http://host.docker.internal:11434`, which doesn't resolve on the host. If Ollama answers on `localhost:11434` but completions fail with 502 (`nodename nor servname provided`), `.env` probably has that value.
  - Don't edit `.env`. Override it for the run with `${CLAUDE_SKILL_DIR}/smoke.sh --ollama-url http://localhost:11434`; process env beats `.env`.
  - Then tell the user.
- **Working directory**: `.env`, `aegis_guard.db` and `src/database/vector_store/` are resolved relative to the CWD, so start the server from the repo root.
- **The seeded key allows 5 requests per minute**: every authenticated request with a valid body counts (a 422 doesn't), including ones that fail upstream. A 429 after a few manual calls is the limiter working.
- **Docker bind mount**: run `seed.py` before the first `docker compose up`. If `./aegis_guard.db` doesn't exist, Docker creates a directory with that name.
- **`docker compose config`** prints the resolved `.env` values. Validate with `docker compose config -q`.
