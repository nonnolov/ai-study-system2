from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Study System"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/aistudy"
    upload_dir: str = "./storage/uploads"
    ai_provider: str = "mock"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    frontend_origin: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
