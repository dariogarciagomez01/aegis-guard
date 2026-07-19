import time
import json
import uuid
from typing import List, Optional, Any
from contextlib import asynccontextmanager
from src.database.connection import init_db
from src.database.vector_db import init_vector_db
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, APIRouter
from fastapi.responses import StreamingResponse
from src.common.factory import ProviderFactory
from pydantic import BaseModel
from src.common.providers import ChatMessage
from src.proxy.auth import authenticate_key
from src.database.models import ApiKey
from src.proxy.limiter import limiter
from src.proxy.embeddings import EmbeddingsEngine
from src.database.vector_db import search_semantic_cache, save_to_cache

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_vector_db(vector_dim=768)
    yield

app = FastAPI(
    title="Aegis Guard Proxy",
    description="High-performance LLM reverse proxy and evaluation gateway",
    version="0.2.0",
    lifespan = lifespan
)

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
                print(f"[TELEMETRY] TTFT for model '{current_model}': {round(ttft_ms, 2)}ms")
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
        print(f"[WARNING] Primary engine '{current_model}' disrupted: {str(upstream_error)}")
        
        # If the failure happens on a cloud provider, execute zero-downtime hot-swap to local
        if "Ollama" not in active_provider.__class__.__name__:
            fallback_model = "llama3"
            print(f"[RESILIENCE] Initiating automatic fallback routing to local engine: '{fallback_model}'")
            
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
                yield f"data: {json.dumps({'error': 'Fatal: Both cloud and local fallback nodes are unresponsive'})}\n\n"
        else:
            # If local engine itself failed, surface error securely
            yield f"data: {json.dumps({'error': f'Local daemon unrecoverable: {str(upstream_error)}'})}\n\n"

    # Standard SSE protocol closure chunk
    yield "data: [DONE]\n\n"


async def cache_response_background(vector: list, prompt: str, response_text: str, model: str):
    """
    Background task to safely write new execution entries into LanceDB
    without hindering or delaying the active client HTTP connection.
    """
    try:
        save_to_cache(vector, prompt, response_text, model)
    except Exception as e:
        print(f"[ERROR-CACHE] Failed to write to semantic cache asynchronously: {str(e)}")

# --- SIMULATE STREAMING ON CACHE HIT ---
async def cached_stream_generator(response_text: str, model: str):
    """
    Simulates a high-speed OpenAI-compliant token stream using pre-cached 
    text data from LanceDB, adding custom Aegis Guard metadata tracking.
    """
    chunk_id = f"chatcmpl-cache-{uuid.uuid4().hex[:16]}"
    created_time = int(time.time())
    
    # Split the cached text by words to mimic natural token generation streaming
    words = response_text.split(" ")
    
    for i, word in enumerate(words):
        # Re-append space delimiter for all words except the trailing token
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
        # Tiny non-blocking sleep (5ms) to give a smooth, blazing-fast stream feel
        await asyncio.sleep(0.005)
        
    # Standard OpenAI protocol final sequence termination chunks
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
    
    # Consume the original stream generator coming from your provider pipeline
    async for chunk in execution_stream_generator(request, provider):
        yield chunk
        
        # Intercept and safely parse text content delta from the active SSE chunk string
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
            # Passive Resilience: If an individual chunk fails parsing, do not drop the client stream connection
            pass
            
    # CRITICAL: Once the stream has been completely drained, offload the text data into LanceDB
    if query_vector and full_response_text:
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
            user_prompt = getattr(last_msg, "content", "") or last_msg.get("content", "")

        query_vector = None
        
        # --- FAST-PATH: SEMANTIC CACHE EVALUATION ---
        if user_prompt:
            try:
                query_vector = await EmbeddingsEngine.get_embedding(user_prompt)
                cache_hit = search_semantic_cache(query_vector, threshold=0.88)
                
                if cache_hit:
                    # STREAMING CACHE HIT ROUTE
                    if request.stream:
                        print(f"[CACHE-HIT] Serving streaming semantic match response.")
                        return StreamingResponse(
                            cached_stream_generator(cache_hit["response_text"], request.model),
                            media_type="text/event-stream"
                        )
                    # STATIC CACHE HIT ROUTE
                    else:
                        latency_seconds = time.perf_counter() - start_time
                        print(f"[CACHE-HIT] Serving static semantic match response in {latency_seconds * 1000:.2f}ms")
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
                print(f"[CACHE-BYPASS] Semantic engine exception: {str(embed_err)}. Falling back to live LLM.")

        provider = ProviderFactory.get_provider(request.model)

        # --- STREAMING CACHE MISS ROUTE ---
        if request.stream:
            print("[CACHE-MISS] Streaming request detected. Wrapping generator to intercept output text.")
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
        
        if query_vector and raw_response:
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
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Proxy Error")