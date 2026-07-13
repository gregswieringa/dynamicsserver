from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://buyer:buyer@localhost:5432/marketplace"


settings = Settings()
