import asyncio
from src.proxy.embeddings import EmbeddingsEngine

async def test():
    print("--- 🔌 TESTEANDO ENDPOINT DE EMBEDDINGS DE OLLAMA ---")
    try:
        vector = await EmbeddingsEngine.get_embedding("Hola, Aegis Guard")
        print("✅ Conexión con Ollama exitosa.")
        print(f"✅ Dimensión del vector devuelto: {len(vector)} (Esperado: 768 para nomic-embed-text)")
        print(f"    Primeros 5 valores: {vector[:5]}")
    except Exception as e:
        print(f"❌ Error al conectar con Ollama: {e}")

if __name__ == "__main__":
    asyncio.run(test())