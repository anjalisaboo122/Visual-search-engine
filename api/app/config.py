from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres Configuration
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "visual_search"

    # Redis Configuration
    redis_host: str = "redis"
    redis_port: int = 6379

    # Storage (RustFS / MinIO S3-compatible) Configuration
    storage_host: str = "storage"
    storage_port: int = 9000
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_secure: bool = False

    # MinIO compatibility aliases
    minio_host: str | None = None
    minio_port: int | None = None
    minio_root_user: str | None = None
    minio_root_password: str | None = None

    # Images
    storage_bucket: str = "images"
    max_upload_mb: int = 10

    # Job queue (Redis Streams)
    queue_stream: str = "image-jobs"
    queue_group: str = "embedders"
    queue_dead_letter_stream: str = "image-jobs-dead"
    queue_max_attempts: int = 3
    # A job a worker took but hasn't finished after this long is assumed
    # stuck (worker crashed) and gets handed to another worker.
    queue_claim_idle_ms: int = 60_000

    # Worker
    embedder: str = "clip"  # "clip" (real) or "fake" (tests, no model download)
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"

    # Auth (JWT) Configuration
    # No default on purpose: if JWT_SECRET is missing, the API refuses to start
    # instead of silently signing tokens with a guessable key.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return value

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def s3_endpoint(self) -> str:
        host = self.minio_host or self.storage_host
        port = self.minio_port or self.storage_port
        return f"{host}:{port}"

    @property
    def s3_access_key(self) -> str:
        return self.storage_access_key or self.minio_root_user or "minioadmin"

    @property
    def s3_secret_key(self) -> str:
        return self.storage_secret_key or self.minio_root_password or "minioadmin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
