from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    openrouter_api_key: str
    nhtsa_base_url: str = "https://vpic.nhtsa.dot.gov/api"
    carquery_base_url: str = "https://www.carqueryapi.com/api/0.3"
    vehicledatabases_api_key: str = "your_vdb_key_here"
    brave_api_key: str = "your_brave_key_here"
    tavily_api_key: str = "your_tavily_key_here"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
