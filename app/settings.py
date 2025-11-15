from pydantic import BaseModel
import os


class Settings(BaseModel):
    env: str = os.getenv("ENV", "dev")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")


settings = Settings()
