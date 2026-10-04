from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+psycopg2://hallspan:hallspan@localhost:5450/hallspan"
    seed_on_empty: bool = True


settings = Settings()
