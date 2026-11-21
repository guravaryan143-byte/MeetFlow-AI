import os
from pathlib import Path
from typing import List


class Settings:
    PROJECT_NAME: str = "MeetFlow AI"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Database (SQLite default for local/sandbox; PostgreSQL+pgvector in production)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(__file__).resolve().parents[2] / 'meetflow.db'}",
    )

    # Security & JWT
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY", "dev-only-change-in-production-meetflow-secret-key-2026"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    # CORS
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
        ).split(",")
        if origin.strip()
    ]

    # File uploads
    UPLOAD_DIR: Path = Path(
        os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parents[2] / "uploads"))
    )
    MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    ALLOWED_AUDIO_EXTENSIONS: set[str] = {
        ".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac"
    }
    ALLOWED_TRANSCRIPT_EXTENSIONS: set[str] = {".txt", ".md", ".vtt", ".srt", ".json"}

    # AI providers are opt-in. "deterministic" is the credential-free local demo mode.
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "deterministic").lower()
    TRANSCRIPTION_PROVIDER: str = os.getenv(
        "TRANSCRIPTION_PROVIDER",
        "openai" if os.getenv("AI_PROVIDER", "deterministic").lower() == "openai" else "deterministic",
    ).lower()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    WHISPER_API_KEY: str = os.getenv("WHISPER_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    OPENAI_TRANSCRIPTION_MODEL: str = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
    OPENAI_CHAT_COMPLETIONS_URL: str = os.getenv(
        "OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions"
    )
    OPENAI_TRANSCRIPTION_URL: str = os.getenv(
        "OPENAI_TRANSCRIPTION_URL", "https://api.openai.com/v1/audio/transcriptions"
    )
    GEMINI_GENERATE_URL: str = os.getenv(
        "GEMINI_GENERATE_URL", "https://generativelanguage.googleapis.com/v1beta/models"
    )
    AI_TIMEOUT_SECONDS: float = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
    AI_MAX_RETRIES: int = int(os.getenv("AI_MAX_RETRIES", "2"))

    INTEGRATION_MODE: str = os.getenv("INTEGRATION_MODE", "mock").lower()

    # External credentials are environment-only and are accessed by AuthorizedExecutionService.
    LINEAR_API_KEY: str = os.getenv("LINEAR_API_KEY", "")
    LINEAR_TEAM_ID: str = os.getenv("LINEAR_TEAM_ID", "")
    TRELLO_API_KEY: str = os.getenv("TRELLO_API_KEY", "")
    TRELLO_TOKEN: str = os.getenv("TRELLO_TOKEN", "")
    TRELLO_LIST_ID: str = os.getenv("TRELLO_LIST_ID", "")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    GOOGLE_CALENDAR_ACCESS_TOKEN: str = os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN", "")
    GOOGLE_CALENDAR_ID: str = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    GOOGLE_CALENDAR_API_URL: str = os.getenv(
        "GOOGLE_CALENDAR_API_URL", "https://www.googleapis.com/calendar/v3"
    )

    DEV_JWT_SECRET: str = "dev-only-change-in-production-meetflow-secret-key-2026"

    def validate(self) -> None:
        """Fail fast on unsafe production configuration."""
        if self.AI_PROVIDER not in {"deterministic", "demo", "local_demo", "openai", "gemini"}:
            raise RuntimeError("AI_PROVIDER must be deterministic, demo, openai, or gemini.")
        if self.TRANSCRIPTION_PROVIDER not in {"deterministic", "openai"}:
            raise RuntimeError("TRANSCRIPTION_PROVIDER must be deterministic or openai.")
        if self.INTEGRATION_MODE not in {"mock", "live"}:
            raise RuntimeError("INTEGRATION_MODE must be 'mock' or 'live'.")
        if self.AI_TIMEOUT_SECONDS <= 0 or not 0 <= self.AI_MAX_RETRIES <= 5:
            raise RuntimeError("AI_TIMEOUT_SECONDS must be positive and AI_MAX_RETRIES must be between 0 and 5.")
        if self.ENVIRONMENT.lower() == "production":
            if self.JWT_SECRET_KEY == self.DEV_JWT_SECRET or len(self.JWT_SECRET_KEY) < 32:
                raise RuntimeError(
                    "Unsafe configuration: set a strong JWT_SECRET_KEY (>= 32 chars) "
                    "when ENVIRONMENT=production."
                )


settings = Settings()
settings.validate()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
