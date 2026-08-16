"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "CramSchool API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/cramschool.db"

    # JWT
    SECRET_KEY: str = "change-me-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "https://cramschool-b4d52.web.app",
        "https://cramschool-b4d52.firebaseapp.com",
        "https://www.gateway2go.bond",
        "https://api.gateway2go.bond",
        "https://www.hsedu.com.tw",
        "https://api.hsedu.com.tw",
    ]

    # Upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 5

    # SMTP (Email)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    FRONTEND_URL: str = "https://www.hsedu.com.tw"

    # Browser Cache (public GET APIs)
    # 九月底 production 前請設 0（更新即時顯示），production 後再調整秒數
    PUBLIC_CACHE_MAX_AGE: int = 0
    PUBLIC_CACHE_STALE_WHILE_REVALIDATE: int = 86400

    def public_cache_control(self) -> str:
        if self.PUBLIC_CACHE_MAX_AGE <= 0:
            return "no-store"
        return (
            f"public, max-age={self.PUBLIC_CACHE_MAX_AGE}, "
            f"stale-while-revalidate={self.PUBLIC_CACHE_STALE_WHILE_REVALIDATE}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()