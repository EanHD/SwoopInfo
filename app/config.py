from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    nhtsa_base_url: str = "https://vpic.nhtsa.dot.gov/api"
    carquery_base_url: str = "https://www.carqueryapi.com/api/0.3"
    vehicledatabases_api_key: str = os.getenv("VEHICLEDATABASES_API_KEY", "")
    brave_api_key: str = os.getenv("BRAVE_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
