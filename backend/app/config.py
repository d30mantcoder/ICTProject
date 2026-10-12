from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Study LMS"
    api_host: str = "0.0.0.0"
    api_port: int = 1734
    database_url: str = "mysql+pymysql://root:@127.0.0.1:3306/study_lms?charset=utf8mb4"
    jwt_secret: str = "development-only-change-me"
    jwt_expire_minutes: int = 480
    cors_origins: str = "http://127.0.0.1:5500,http://localhost:5500"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
