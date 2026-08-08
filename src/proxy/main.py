import time
import json
import os
import uuid
import asyncio
from typing import List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from src.database.connection import init_db
from src.database.vector_db import init_vector_db, search_semantic_cache, save_to_cache
from src.common.factory import ProviderFactory
from src.common.providers import ChatMessage
from src.proxy.auth import authenticate_key
from src.database.models import ApiKey
from src.proxy.limiter import limiter
from src.proxy.embeddings import EmbeddingsEngine
from src.utils.logger import logger

DISABLE_SEMANTIC_CACHE = os.getenv("DISABLE_SEMANTIC_CACHE", "false").lower() in ("true", "1")

# --- PROMETHEUS METRICS DEFINITION ---
REQUEST_COUNT = Counter(
    "aegis_guard_requests_total",
    "Total HTTP requests handled by Aegis Guard",
    ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "aegis_guard_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"]
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_vector_db(vector_dim=768)
    logger.info("Application startup: Databases initialized")
    yield

app = FastAPI(
    title="Aegis Guard Proxy",
    description="High-performance LLM reverse proxy and evaluation gateway",
    version="0.2.0",
    lifespan=lifespan
)

# --- GLOBAL OBSERVABILITY MIDDLEWARE ---
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    
    auth_header = request.headers.get("Authorization", "")
    api_key_suffix = auth_header[-6:] if len(auth_header) >= 6 else "none"
    client_ip = request.client.host if request.client else "unknown"

    try:
        response: Response = await call_next(request)
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Ignore /metrics endpoint to avoid polluting operational telemetry
        if request.url.path != "/metrics":
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code
            ).inc()
            
            REQUEST_LATENCY.labels(endpoint=request.url.path).observe(process_time_ms / 1000.0)

            log_payload = {
                "client_ip": client_ip,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": process_time_ms,
                "api_key_suffix": api_key_suffix
            }

            if response.status_code < 400:
                logger.info("Request processed successfully", extra={"extra_data": log_payload})
            elif response.status_code == 429:
                logger.warning("Rate limit threshold exceeded", extra={"extra_data": log_payload})
            else:
                logger.error("Request execution failed", extra={"extra_data": log_payload})

        return response

    except Exception as exc:
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        log_payload = {
            "client_ip": client_ip,
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "latency_ms": process_time_ms,
            "error": str(exc)
        }
        logger.critical("Unhandled proxy exception", extra={"extra_data": log_payload}, exc_info=True)
        raise exc

# Schema matching the OpenAI standard for incoming requests
class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False

async def execution_stream_generator(request: ChatCompletionRequest, primary_provider: Any) -> Any:
    """
    Core generator engine handling sequential token transmission,
    silent hot-swap infrastructure fallback, and TTFT metrics gathering.
    """
    start_time = time.perf_counter()
    ttft_measured = False
    active_provider = primary_provider
    current_model = request.model

    created_time = int(time.time())
    stream_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
    
    try:
        # Step 1: Attempt to establish network stream pool with the primary provider
        stream = active_provider.generate_stream(
            messages=request.messages, 
            temperature=request.temperature
        )
        
        async for token in stream:
            # Calculate Time To First Token (TTFT) precisely
            if not ttft_measured:
                ttft_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "TTFT measured",
                    extra={"extra_data": {"model": current_model, "ttft_ms": round(ttft_ms, 2)}}
                )
                ttft_measured = True
                
            # Build standard-compliant OpenAI chunk payload
            chunk_payload = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": current_model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": token},
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(chunk_payload)}\n\n"
            
    except Exception as upstream_error:
        # Active Fault-Tolerant Fallback Interceptor
        logger.warning(
            "Primary engine disrupted",
            extra={"extra_data": {"model": current_model, "error": str(upstream_error)}}
        )
        
        # If the failure happens on a cloud provider, execute zero-downtime hot-swap to local
        if "Ollama" not in active_provider.__class__.__name__:
            fallback_model = "llama3"
            logger.info(
                "Initiating fallback routing",
                extra={"extra_data": {"fallback_model": fallback_model}}
            )
            
            try:
                fallback_provider = ProviderFactory.get_provider(fallback_model)
                fallback_stream = fallback_provider.generate_stream(
                    messages=request.messages,
                    temperature=request.temperature
                )
                
                async for token in fallback_stream:
                    chunk_payload = {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": f"{fallback_model}-fallback",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": token},
                                "finish_reason": None
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk_payload)}\n\n"
            except Exception as fallback_fatal:
                logger.error(
                    "Fallback engine failed",
                    extra={"extra_data": {"error": str(fallback_fatal)}}
                )
                yield f"data: {json.dumps({'error': 'Fatal: Both cloud and local fallback nodes are unresponsive'})}\n\n"
        else:
            yield f"data: {json.dumps({'error': f'Local daemon unrecoverable: {str(upstream_error)}'})}\n\n"

    stop_payload = {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": current_model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(stop_payload)}\n\n"

    # Standard SSE protocol closure chunk
    yield "data: [DONE]\n\n"


async def cache_response_background(vector: list, prompt: str, response_text: str, model: str):
    """
    Background task to safely write new execution entries into LanceDB
    without hindering or delaying the active client HTTP connection.
    """
    try:
        save_to_cache(vector, prompt, response_text, model)
        logger.info("Asynchronous semantic cache write successful", extra={"extra_data": {"model": model}})
    except Exception as e:
        logger.error(
            "Failed to write to semantic cache asynchronously",
            extra={"extra_data": {"error": str(e)}}
        )


# --- SIMULATE STREAMING ON CACHE HIT ---
async def cached_stream_generator(response_text: str, model: str):
    """
    Simulates a high-speed OpenAI-compliant token stream using pre-cached 
    text data from LanceDB, adding custom Aegis Guard metadata tracking.
    """
    chunk_id = f"chatcmpl-cache-{uuid.uuid4().hex[:16]}"
    created_time = int(time.time())
    
    words = response_text.split(" ")
    
    for i, word in enumerate(words):
        space = " " if i < len(words) - 1 else ""
        content_chunk = word + space
        
        chunk_payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content_chunk},
                    "finish_reason": None
                }
            ],
            "_aegis_guard_meta": {
                "provider": "semantic_cache",
                "status": "cached_stream_hit"
            }
        }
        yield f"data: {json.dumps(chunk_payload)}\n\n"
        await asyncio.sleep(0.005)
        
    stop_payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(stop_payload)}\n\n"
    yield "data: [DONE]\n\n"


# --- INTERCEPT AND CONCATENATE LIVE STREAM ON CACHE MISS ---
async def caching_stream_generator(request, provider, query_vector, user_prompt, background_tasks: BackgroundTasks):
    """
    Wraps the live upstream LLM streaming response. Intercepts incoming chunks on the fly 
    to reconstruct the full answer string, and triggers a background cache write upon stream exhaustion.
    """
    full_response_text = ""
    
    async for chunk in execution_stream_generator(request, provider):
        yield chunk
        
        try:
            chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            if chunk_str.startswith("data: ") and "[DONE]" not in chunk_str:
                data_body = chunk_str[6:].strip()
                data_json = json.loads(data_body)
                choices = data_json.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_response_text += content
        except Exception:
            pass
            
    if query_vector and full_response_text and not DISABLE_SEMANTIC_CACHE:
        background_tasks.add_task(
            cache_response_background,
            query_vector,
            user_prompt,
            full_response_text,
            request.model
        )

@app.get("/health")
async def health_check():
    """Simple health endpoint to verify the proxy is live."""
    return {"status": "healthy", "service": "aegis-guard-proxy"}

@app.get("/metrics", include_in_schema=False)
def metrics():
    """Exposes Prometheus operational metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    api_key: ApiKey = Depends(authenticate_key)
):
    """
    Intercepts LLM requests, evaluates semantic cache hits (static/streaming), routes queries 
    dynamically, measures high-resolution latency, and captures background caching streams.
    """
    if await limiter.is_rate_limited(api_key.key, api_key.rate_limit_rpm):
        logger.warning(
            "Rate limit exceeded",
            extra={"extra_data": {"user_id": api_key.user_id, "limit": api_key.rate_limit_rpm}}
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "message": "Requests rate limit exceeded. Please try again later.",
                    "type": "requests_limit_reached",
                    "param": None,
                    "code": "429"
                }
            }
        )
    
    start_time = time.perf_counter()

    try:
        user_prompt = ""
        if request.messages:
            last_msg = request.messages[-1]
            user_prompt = getattr(last_msg, "content", "") or (last_msg.get("content", "") if isinstance(last_msg, dict) else "")

        query_vector = None
        
        # --- FAST-PATH: SEMANTIC CACHE EVALUATION ---
        if user_prompt and not DISABLE_SEMANTIC_CACHE:
            try:
                query_vector = await EmbeddingsEngine.get_embedding(user_prompt)
                cache_hit = await asyncio.to_thread(search_semantic_cache, query_vector, 0.88)
                
                if cache_hit:
                    # STREAMING CACHE HIT ROUTE
                    if request.stream:
                        logger.info(
                            "Serving streaming semantic cache match",
                            extra={"extra_data": {"type": "stream", "model": request.model}}
                        )
                        return StreamingResponse(
                            cached_stream_generator(cache_hit["response_text"], request.model),
                            media_type="text/event-stream"
                        )
                    # STATIC CACHE HIT ROUTE
                    else:
                        latency_seconds = time.perf_counter() - start_time
                        logger.info(
                            "Serving static semantic cache match",
                            extra={
                                "extra_data": {
                                    "type": "static",
                                    "latency_ms": round(latency_seconds * 1000, 2),
                                    "similarity_score": round(cache_hit["similarity_score"], 4)
                                }
                            }
                        )
                        return {
                            "id": f"chatcmpl-cache-{uuid.uuid4().hex[:16]}",
                            "object": "chat.completion",
                            "created": int(time.time()),
                            "model": cache_hit["model_used"],
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {"role": "assistant", "content": cache_hit["response_text"]},
                                    "finish_reason": "stop"
                                }
                            ],
                            "_aegis_guard_meta": {
                                "latency_ms": round(latency_seconds * 1000, 2),
                                "provider": "semantic_cache",
                                "status": "cached_hit",
                                "similarity_score": round(cache_hit["similarity_score"], 4)
                            }
                        }
            except Exception as embed_err:
                logger.warning(
                    "Semantic engine exception, falling back to live LLM",
                    extra={"extra_data": {"error": str(embed_err)}}
                )

        provider = ProviderFactory.get_provider(request.model)

        # --- STREAMING CACHE MISS ROUTE ---
        if request.stream:
            logger.info(
                "Cache miss: streaming request detected",
                extra={"extra_data": {"model": request.model}}
            )
            return StreamingResponse(
                caching_stream_generator(request, provider, query_vector, user_prompt, background_tasks),
                media_type="text/event-stream"
            )

        # --- STATIC CACHE MISS ROUTE ---
        static_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        static_created_time = int(time.time())

        raw_response = await provider.generate(
            messages=request.messages, 
            temperature=request.temperature
        )
        
        latency_seconds = time.perf_counter() - start_time
        provider_name = provider.__class__.__name__.replace("Provider", "").lower()
        
        logger.info(
            "Live LLM request processed",
            extra={
                "extra_data": {
                    "provider": provider_name,
                    "model": request.model,
                    "latency_ms": round(latency_seconds * 1000, 2)
                }
            }
        )

        if query_vector and raw_response and not DISABLE_SEMANTIC_CACHE:
            background_tasks.add_task(
                cache_response_background,
                query_vector,
                user_prompt,
                raw_response,
                request.model
            )
        
        return {
            "id": static_id,
            "object": "chat.completion",
            "created": static_created_time,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": raw_response},
                    "finish_reason": "stop"
                }
            ],
            "_aegis_guard_meta": {
                "latency_ms": round(latency_seconds * 1000, 2),
                "provider": provider_name,
                "status": "intercepted_and_processed"
            }
        }
        
    except RuntimeError as e:
        logger.error("Provider execution error", extra={"extra_data": {"error": str(e)}})
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("Internal Proxy Error", extra={"extra_data": {"error": str(e)}})
        raise HTTPException(status_code=500, detail="Internal Proxy Error")