import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from src.common.factory import ProviderFactory
from pydantic import BaseModel
from src.common.providers import ChatMessage

app = FastAPI(
    title="Aegis Guard Proxy",
    description="High-performance LLM reverse proxy and evaluation gateway",
    version="0.1.0"
)

# Schema matching the OpenAI standard for incoming requests
class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7

@app.get("/health")
async def health_check():
    """Simple health endpoint to verify the proxy is live."""
    return {"status": "healthy", "service": "aegis-guard-proxy"}

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    Intercepts LLM requests, routes them dynamically via ProviderFactory,
    measures high-resolution network latency, and injects custom metadata.
    """
    # Start high-resolution performance clock
    start_time = time.perf_counter()
    
    try:
        # Instantiate the local provider dynamically using the requested model
        provider = ProviderFactory.get_provider(request.model)
        
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
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
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