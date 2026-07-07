from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    LLM_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    DB_PATH: str = "civic.db"
    OLLAMA_HOST: str = "http://localhost:11434"

    class Config:
        env_file = ".env"

settings = Settings()
