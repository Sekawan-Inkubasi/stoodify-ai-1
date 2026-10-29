import pytest


@pytest.fixture(autouse=True)
def tanpa_key_llm_asli(monkeypatch):
    """Pastikan tes tidak pernah memanggil LLM sungguhan, walau ada .env di laptop."""
    for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL",
              "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "AI_TIMEOUT_SECONDS"):
        monkeypatch.delenv(k, raising=False)
