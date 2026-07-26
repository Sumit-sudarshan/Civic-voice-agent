from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # --- LLM backend selection ---
    # Reasoning only (gatekeeper, classify, urgency, extract, dialogue manager):
    #   GROQ_API_KEY set             -> Groq (GROQ_MODEL)
    #   else OPENROUTER_API_KEY set  -> OpenRouter (OPENROUTER_MODEL)   <- MVP default
    #   else                         -> Ollama (OLLAMA_LLM_MODEL)
    # Embeddings are ALWAYS local Ollama (EMBEDDING_MODEL). By design the dedup
    # vectors are derived from PII-bearing complaint text, so that text never
    # leaves the VM — it is not routed through any hosted API regardless of the
    # reasoning backend. See MVP_Design.md §3.1.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OLLAMA_LLM_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # --- Database ---
    # Supabase-managed Postgres in every environment (no separate local DB).
    # Must be the Supavisor transaction-mode pooler URL (port 6543):
    #   postgresql+psycopg2://postgres.<ref>:<pw>@<host>.pooler.supabase.com:6543/postgres
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"

    # --- Supabase Auth (wired up in Phase 3; read at startup from now on so
    # config validation doesn't break when these are already in .env) ---
    # PUBLISHABLE_KEY: safe for client use (anon-key equivalent).
    # SECRET_KEY: service-role equivalent — bypasses RLS, server-side only,
    # never sent to the frontend. Both come from Secret Manager in prod.
    PUBLISHABLE_KEY: str = ""
    SECRET_KEY: str = ""
    SUPABASE_URL: str = "https://lygnuqonfnedkrinlcqo.supabase.co"

    # --- CORS ---
    # Comma-separated list of allowed origins. "*" (dev default) allows any
    # origin; set to the deployed frontend's exact origin(s) in production.
    ALLOWED_ORIGINS: str = "*"

    # Resolved at startup from the settings above — don't set this directly
    # in .env. Kept as a real mutable field (not a computed property) so eval
    # scripts' `--model` override (`settings.LLM_MODEL = ...`) keeps working
    # exactly as before.
    LLM_MODEL: str = ""

    # Access token for the gated IndicTrans2 model on Hugging Face (Hindi/
    # Marathi translation). Optional — if empty, translation.py falls back to
    # passing Hindi/Marathi text through untranslated instead of crashing.
    HF_TOKEN: str = ""

    OLLAMA_HOST: str = "http://localhost:11434"
    # Ollama performance tuning
    OLLAMA_KEEP_ALIVE: str = "10m"   # Keep model loaded for 10 min across pipeline calls
    OLLAMA_NUM_THREAD: int = 4       # Set to your CPU core count (override via .env)
    OLLAMA_NUM_CTX: int = 2048       # Headroom for extraction's 5 few-shot examples + schema hint

    # --- LLM call timeouts & retries (NFR7/NFR8) ---
    # Sync loop = gatekeeper/dialogue-manager/reply-composer, run inline while
    # the citizen is waiting on an HTTP response — a safety net, not a target
    # (too low and the fallback path becomes the common path). Async loop =
    # classify/urgency/extract/embed, run in the background finalize task
    # where nobody's actively waiting, so it can afford to try harder before
    # falling back to needs_human_review.
    SYNC_LLM_TIMEOUT_S: float = 9.0
    SYNC_LLM_RETRIES: int = 2                       # 3 attempts total
    SYNC_LLM_BACKOFF_S: list[float] = [1.0, 3.0]
    ASYNC_LLM_TIMEOUT_S: float = 20.0
    ASYNC_LLM_RETRIES: int = 3                      # 4 attempts total
    ASYNC_LLM_BACKOFF_S: list[float] = [2.0, 5.0, 10.0]

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Always recompute (not just "if empty") so a stray leftover
        # LLM_MODEL=/EMBED_MODEL= line in an old .env file can never shadow this.
        if self.GROQ_API_KEY:
            self.LLM_MODEL = self.GROQ_MODEL
        elif self.OPENROUTER_API_KEY:
            self.LLM_MODEL = self.OPENROUTER_MODEL
        else:
            self.LLM_MODEL = self.OLLAMA_LLM_MODEL

settings = Settings()
