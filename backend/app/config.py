from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # --- LLM backend selection ---
    # If GROQ_API_KEY is set, Groq handles all reasoning calls (gatekeeper,
    # classify, urgency, extract, dialogue manager) using GROQ_MODEL, and
    # Ollama is used ONLY for embeddings (EMBEDDING_MODEL) — Groq has no
    # embeddings endpoint. Leave GROQ_API_KEY empty/commented to fall back to
    # Ollama for everything instead (reasoning via OLLAMA_LLM_MODEL,
    # embeddings via EMBEDDING_MODEL). Both model names live in .env at once,
    # so switching backends is just toggling GROQ_API_KEY — nothing else to edit.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    OLLAMA_LLM_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # Resolved at startup from the two model settings above — don't set this
    # directly in .env. Kept as a real mutable field (not a computed
    # property) so eval scripts' `--model` override (`settings.LLM_MODEL =
    # ...`) keeps working exactly as before.
    LLM_MODEL: str = ""

    # Access token for the gated IndicTrans2 model on Hugging Face (Hindi/
    # Marathi translation). Optional — if empty, translation.py falls back to
    # passing Hindi/Marathi text through untranslated instead of crashing.
    HF_TOKEN: str = ""

    DB_PATH: str = "civic.db"
    OLLAMA_HOST: str = "http://localhost:11434"
    # Ollama performance tuning
    OLLAMA_KEEP_ALIVE: str = "10m"   # Keep model loaded for 10 min across pipeline calls
    OLLAMA_NUM_THREAD: int = 4       # Set to your CPU core count (override via .env)
    OLLAMA_NUM_CTX: int = 2048       # Headroom for extraction's 5 few-shot examples + schema hint

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Always recompute (not just "if empty") so a stray leftover
        # LLM_MODEL= line in an old .env file can never shadow this.
        self.LLM_MODEL = self.GROQ_MODEL if self.GROQ_API_KEY else self.OLLAMA_LLM_MODEL

settings = Settings()
