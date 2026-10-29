# CLAUDE.md

Aegis Guard is an OpenAI-compatible LLM gateway built with FastAPI. Clients call `POST /v1/chat/completions` (JSON or SSE streaming). The gateway:

- authenticates a Bearer API key;
- applies a per-key rate limit;
- checks a semantic cache;
- forwards the request to Ollama (local models) or OpenAI (`gpt-*`).

It also serves `GET /health`, Prometheus `GET /metrics` and Swagger at `/docs`, and logs JSON lines. The project is built milestone by milestone (plans in `docs/working plans/`). AWS ECS Fargate infrastructure lives in `terraform/`.

## Working with the maintainer

- **This is a learning project.** It exists to build the maintainer's knowledge and CV, not to ship fast.
  - Work in small, reviewable steps and explain why: the approach, the alternatives, what to look at.
  - List every file you touched.
  - Prefer teaching and guiding over silently doing everything.
- **Never run `git add`, `git commit` or `git push`.** `.claude/settings.json` denies add/commit. When a change is ready, reply with only:
  - a one-line Conventional Commits message (no body, no `Co-Authored-By` or other trailers);
  - the exact list of paths to stage.

## Ground rules

- **Where to run things**: start Claude Code from the repo root and run every command from there.
  - `.claude/settings.json` (permissions and hooks) is read only from the directory Claude Code starts in.
  - Imports use the `src.` prefix (namespace packages, no `__init__.py`).
  - `.env`, `aegis_guard.db` and `src/database/vector_store/` are resolved relative to the working directory.
- **Editing files**: edit `.py` and `.tf` files with the Edit/Write tools, not `sed -i` or heredocs. The post-edit hook and the `.claude/rules/` files only trigger on those tools.
- **Language**: write new code, comments, commit messages and docs in English. Leave the existing Spanish text alone unless asked (script output in `seed.py`/`tests/`, a few comments, and a Terraform description).
- **Secrets**:
  - Claude's file tools and `cat`/`head`/`tail`/`sed` are denied `.env`, `*.tfstate*` and `*.tfvars*`. Commands that read files without naming them aren't covered.
  - Search with the Grep tool or `git grep` (both skip gitignored files), not `grep -r … .`.
  - Never `source` `.env` or print the `settings` object (it holds `OPENAI_API_KEY`).
  - Never run `docker compose config` without `-q`, or `docker inspect`/`exec … env` on the container: compose loads `.env` into it.
- **New settings**: add a typed field with a safe default to `Settings` (`src/common/config.py`), plus a placeholder line in `.env.example`. Then tell the user what to put in `.env`.
- **Dev data**: `aegis_guard.db` holds the API keys. The seeded dev key `ak_live_dario123456789` is already public in `seed.py`; don't print any other key.
- **Public repo**: `dariogarciagomez01/aegis-guard` is public, so anything committed or pushed is public.
- **Get the user's go-ahead** before anything that leaves this machine or is hard to undo:
  - Terraform `plan`/`apply`/`destroy`/`refresh`/state changes, and any `aws` command.
  - Image pushes, `git push`, PRs and issues, other `gh` writes.
  - Dependency changes (`poetry add/remove/lock/update`).
  - Deleting `aegis_guard.db`, the vector store or the Terraform state (including `git clean`).
  - Starting Ollama or pulling models.
  - Completions sent to cloud models (`gpt-*`) through the gateway. These are paid calls.

  `.claude/settings.json` forces a prompt for the common forms of these. Treat the rest of each category the same way.

## Commands

| Task | Command |
| --- | --- |
| Install dependencies (in-project `.venv`, `package-mode = false`) | `poetry install` |
| Create the DB and the dev user/key (idempotent) | `poetry run python seed.py` |
| Run locally with reload | `poetry run uvicorn src.proxy.main:app --reload --port 8000` |
| Launch + smoke-test (agent path) | `/run-aegis-guard` skill; re-runs: `.claude/skills/run-aegis-guard/smoke.sh [--keep \| --stop \| --no-cache]` |
| Health / metrics | `curl -s http://localhost:8000/health` · `curl -s http://localhost:8000/metrics` |
| Ollama status (doesn't start it) | `curl -s http://localhost:11434/api/tags` |
| Docker | `docker compose up --build -d` · `docker compose logs --tail 100 aegis-guard` · `docker compose down` |
| Ollama embeddings check | `poetry run python -m tests.test_ollama_embed` |
| Load test | `TEST_API_KEY=ak_live_dario123456789 poetry run locust -f locustfile.py --headless -u 10 -r 2 -t 1m --host http://localhost:8000` |
| Terraform format / validate (offline) | `terraform -chdir=terraform fmt -check -recursive` (drop `-check` to rewrite) · `terraform -chdir=terraform validate` |
| Validate the compose file | `docker compose config -q` |

- **Ollama**:
  - Completions need the daemon on `:11434` with `llama3`. The semantic cache needs `nomic-embed-text`; without it, requests skip the cache. Server startup needs neither.
  - On macOS, `ollama list` launches the Ollama app when it isn't running, so check status with `curl` instead.
  - For Docker, start Ollama with `OLLAMA_HOST=0.0.0.0:11434 ollama serve` and set `OLLAMA_BASE_URL=http://host.docker.internal:11434`. That is the value `.env.example` ships, and it doesn't resolve for a local, non-Docker run.
- **Docker**:
  - Run `seed.py` before the first `docker compose up`. Compose bind-mounts `./aegis_guard.db`, and if the file is missing, Docker creates a directory with that name.
  - `logs -f` never returns, so leave it to humans.
- **Tests**: there is no automated test suite yet. `tests/test_ollama_embed.py` is a manual script that always exits 0. `poetry run pytest` collects it as an unmarked `async def` and reports it as failed: pytest-asyncio isn't installed, and the installed anyio plugin only runs tests marked `@pytest.mark.anyio`.

## Architecture

The request path for `POST /v1/chat/completions` (in `src/proxy/main.py` unless noted):

1. `observability_middleware` times the request, updates `aegis_guard_requests_total` and `aegis_guard_request_duration_seconds`, and writes one JSON log line. `/metrics` is skipped.
2. `authenticate_key` (`src/proxy/auth.py`) checks the `HTTPBearer` token against SQLite. It needs an active `ApiKey` whose `User` is active; otherwise the response is a 401 `{"detail": "..."}`.
3. `limiter.is_rate_limited` (`src/proxy/limiter.py`) applies an in-memory 60 s sliding window per key, limited to `ApiKey.rate_limit_rpm`. Over the limit, the response is a 429 `{"detail": {"error": {message, type, param, code}}}`, an OpenAI-style error under FastAPI's `detail`.
4. The semantic cache runs unless `DISABLE_SEMANTIC_CACHE` is true:
   - It embeds the last message with Ollama `nomic-embed-text` (`src/proxy/embeddings.py`) and searches LanceDB for the nearest neighbour (`src/database/vector_db.py`).
   - Cosine similarity ≥ 0.88 is a hit, served as cached JSON or a simulated stream.
   - Embedding or cache errors are logged, and the request continues live.
5. `ProviderFactory.get_provider(model)` (`src/common/factory.py`): models starting with `gpt-` or containing `openai` go to `OpenAIProvider`; everything else goes to `OllamaProvider`.
6. Non-streaming: `provider.generate()` returns the completion text, which the route wraps in a `chat.completion` JSON. A `RuntimeError` from the provider becomes a 502.
7. Streaming: `execution_stream_generator` sends `chat.completion.chunk` SSE events, then a stop chunk, then `data: [DONE]`.
   - If a non-Ollama provider raises, it falls back to Ollama `llama3`.
   - Failures after the stream has started arrive in-band as `data: {"error": ...}` under HTTP 200.
   - Live answers are queued for a cache write via FastAPI `BackgroundTasks` (`cache_response_background`).

JSON responses add `_aegis_guard_meta`: `latency_ms`, `provider` (`ollama`/`openai`/`semantic_cache`), `status`, and `similarity_score` on cache hits. Cache-hit SSE chunks carry `provider` and `status` only; live SSE chunks carry none. The lifespan hook creates the SQLite tables and the LanceDB table (768-dim vectors) at startup.

| Path | Role |
| --- | --- |
| `src/proxy/main.py` | FastAPI app, lifespan, middleware, routes, SSE generators, Prometheus metrics |
| `src/proxy/auth.py` · `limiter.py` · `embeddings.py` | Bearer-key dependency · `InMemoryRateLimiter` singleton · `EmbeddingsEngine` (Ollama `/api/embeddings`) |
| `src/common/providers.py` | `BaseProvider` contract (`generate() -> str`, `generate_stream()` yielding text tokens) and `ChatMessage` |
| `src/common/ollama_provider.py` · `openai_provider.py` | Adapters for Ollama `/api/chat` and OpenAI `/v1/chat/completions` |
| `src/common/factory.py` · `config.py` | Model-name routing · `Settings` (pydantic-settings, reads `.env`) |
| `src/database/models.py` · `connection.py` · `vector_db.py` | SQLModel `User`/`ApiKey` · engine + `get_session` · LanceDB `semantic_cache` table |
| `src/utils/logger.py` | JSON formatter and the `logger` singleton |
| `seed.py` · `locustfile.py` · `tests/` | Dev seeding · load test · manual Ollama check |
| `terraform/` | AWS infra: ECR, default VPC, security group, IAM, CloudWatch logs, ECS Fargate |
| `docs/` | `DEPLOYMENT.md`, milestone plans, diagrams (StarUML source `Untitled.mdj`), benchmark image |

## Configuration and local state

| Variable | Read by | Default | Notes |
| --- | --- | --- | --- |
| `OLLAMA_BASE_URL` | `Settings` (env, else `.env`) | `http://localhost:11434` | Docker: `http://host.docker.internal:11434` |
| `OPENAI_API_KEY` | `Settings` | empty | Used for `gpt-*` models |
| `DISABLE_SEMANTIC_CACHE` | `os.getenv` at import (`main.py`) | `false` | Process env only. Compose injects `.env`; locally, export it |
| `DATABASE_URL` | `os.getenv` (`connection.py`) | `sqlite:///aegis_guard.db` | Process env only |
| `SEMANTIC_CACHE_THRESHOLD` | — | — | Listed in `.env.example` and the README; the code uses the literal `0.88` |
| `TEST_API_KEY` | `locustfile.py` | the seed key | |

Both state locations below are gitignored local dev data. Don't delete them without asking.

- `aegis_guard.db` (SQLite) holds the users and keys. `seed.py` creates user `dario_dev` with key `ak_live_dario123456789`, limited to 5 requests per minute.
- `src/database/vector_store/` holds the LanceDB semantic cache: `nomic-embed-text` vectors, 768 dimensions, fixed when the table is created.

## Conventions

- **Commits** (the maintainer makes them): Conventional Commits, one subject line, with no body and no trailers.
  - The type and description are lowercase, and the description starts with an imperative verb (`implement`, `configure`, `deploy`). Acronyms keep their case (`ECS`, `IAM`, `SQLite`). No trailing period.
  - Types in use: `feat`, `docs`. Terraform work uses `feat(infra): …`.
  - Examples: `feat: implement rate limiter, auth guard and SQLite`, `feat(infra): configure default vpc and security group`.
- **Branches and PRs**: work happens on `feature/<name>` branches (`feature/milestone-N`, `feature/aws-terraform-deployment`). Each goes into `main` through a PR merged with a merge commit, and branches are kept afterwards.
- **Milestones**:
  - Milestones 1–6 have plans at `docs/working plans/PLAN_NN.md`. Quote that path; it contains a space. `feature/milestone-7` (PR #31, the v1.0 docs pass) has no plan, and neither does the Terraform work.
  - From PLAN_02 on, roadmap tasks are titled `task N.M: <title>` and mostly mirrored as GitHub issues.
  - Shipped tasks get ` (DONE)` on their description line. PLAN_06 hasn't been marked yet, so check git history before trusting the markers.
  - `/new-milestone-plan` drafts a new plan.
- **Code style**: `.claude/rules/python.md` covers Python and loads when `.py` files are touched. `.claude/rules/terraform.md` covers `terraform/`.

## Claude Code setup in this repo

- **`.claude/settings.json` allow rules** are ignored until the workspace trust dialog has been accepted once in an interactive `claude` session at the repo root (`claude -p` never shows it). Deny and ask rules always apply.
- **Hooks**:
  - After Edit/Write, `.claude/hooks/post-edit-check.sh` syntax-checks `.py` files with the 3.11 grammar and runs `terraform fmt` on `.tf` files. A failure comes back as an error to fix.
  - At session start, `.claude/hooks/session-context.sh` prints git, Ollama (with models), gateway, Docker and Terraform-state status.
- **Personal overrides**: personal, uncommitted overrides go in `CLAUDE.local.md` or `.claude/settings.local.json`. Both are gitignored.
