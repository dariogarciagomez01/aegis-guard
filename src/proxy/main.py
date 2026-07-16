import time
import json
import uuid
from typing import List, Optional, Any
from contextlib import asynccontextmanager
from src.database.connection import init_db
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from src.common.factory import ProviderFactory
from pydantic import BaseModel
from src.common.providers import ChatMessage
from src.proxy.auth import authenticate_key
from src.database.models import ApiKey
from src.proxy.limiter import limiter

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

@app.get("/health")
async def health_check():
    """Simple health endpoint to verify the proxy is live."""
    return {"status": "healthy", "service": "aegis-guard-proxy"}

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: ApiKey = Depends(authenticate_key)
    ):
    """
    Intercepts LLM requests, routes them dynamically via ProviderFactory,
    measures high-resolution network latency, and injects custom metadata.
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
    
    try:
        # Instantiate the local provider dynamically using the requested model
        provider = ProviderFactory.get_provider(request.model)
        

        # CONNECTING THE PIPELINE: Branch to streaming generator if requested
        if request.stream:
            return StreamingResponse(
                execution_stream_generator(request, provider),
                media_type="text/event-stream"
            )

        static_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        static_created_time = int(time.time())

        # Modus operandi traditional (Static Response)
        start_time = time.perf_counter()
    
        # Await the asynchronous request to the local Ollama daemon
        raw_response = await provider.generate(
            messages=request.messages, 
            temperature=request.temperature
        )
        
        # Calculate precise latency in milliseconds
        end_time = time.perf_counter()
        latency_seconds = end_time - start_time

        # Dynamically extract provider identity (e.g., "OllamaProvider" -> "ollama")
        provider_name = provider.__class__.__name__.replace("Provider", "").lower()
        
        # Build standard compliance payload + Aegis Guard telemetry
        return {
            "id": static_id,
            "object": "chat.completion",
            "created": static_created_time,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": raw_response
                    },
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
        # Map our custom provider connection/status errors to HTTP 502 Bad Gateway
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        # Global catch-all shield to protect internal infrastructure logs
        raise HTTPException(status_code=500, detail=f"Internal Proxy Error")