"""
Talk to a local LLM through Ollama (free, data stays on your laptop).
  Chat model:      llama3.2           (ollama pull llama3.2)
  Embedding model: nomic-embed-text   (ollama pull nomic-embed-text)  -- optional
Change with env vars: LLM_MODEL, EMBED_MODEL, OLLAMA_URL
"""
import json
import os
import urllib.request

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


def _post(path, body, timeout=180):
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ollama_up():
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def ask_llm(system, user):
    out = _post("/api/generate", {"model": LLM_MODEL, "system": system, "prompt": user,
                                  "stream": False, "options": {"temperature": 0, "num_ctx": 8192}})
    return out["response"]


def embed(texts):
    """Real embeddings via Ollama. Returns a list of vectors."""
    out = _post("/api/embed", {"model": EMBED_MODEL, "input": texts})
    return out["embeddings"]
