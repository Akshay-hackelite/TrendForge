from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "supersecretkeychangeit"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    # Local default; production: https://api.xyz/google.callback
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/google.callback"

    # Where the React app lives (OAuth success redirect)
    # Local: http://localhost:5173  |  Production: https://app.xyz
    FRONTEND_URL: str = "http://localhost:5173"

    # Backend base URL for constructing internal asset links
    # Local: http://localhost:8000  |  Production: https://api.app.xyz
    BASE_URL: str = "http://localhost:8000"

    # Comma-separated origins. Local Vite + future app.xyz
    CORS_ORIGINS: str = "http://localhost:5173,https://app.xyz"

    # Optional. When set, data is stored in flat Mongo collections
    # (users, clients, channels, videos, topics, content_plans)
    MONGODB_URI: str = ""
    MONGODB_DB_NAME: str = "youtube_analytics"

    # File storage: "supabase" (default) or "gcs" (paid Google Cloud later)
    STORAGE_BACKEND: str = "supabase"

    # Supabase Storage. Bucket must be public for Instagram/Facebook.
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_BUCKET: str = "media"

    # Google Cloud Storage — kept for later / mixed-history deletes
    GCS_BUCKET_NAME: str = ""
    GCS_KEY_JSON: str = ""

    # Cron jobs (POST /cron/social.*) — set a long random string; scheduler sends X-Cron-Secret
    CRON_SECRET: str = ""

    # /admin dashboard gate (reset passwords, create users)
    ADMIN_PASSWORD: str = ""

    # Optional first-boot demo user (leave username empty in production)
    SEED_DEMO_USERNAME: str = ""
    SEED_DEMO_PASSWORD: str = ""

    # OpenAI — gpt-5.6-luna for all text tasks (extraction, mapping, generation)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.6-luna"
    OPENAI_REASONING_EFFORT: str = "low"
    OPENAI_EXTRACTION_MODEL: str = "gpt-5.6-luna"
    OPENAI_MAPPING_MODEL: str = "gpt-5.6-luna"
    OPENAI_GENERATION_MODEL: str = "gpt-5.6-luna"
    OPENAI_CONTENT_PLAN_MODEL: str = "gpt-5.6-luna"
    OPENAI_CONTENT_PLAN_MAP_EFFORT: str = "low"
    OPENAI_IMAGE_MODEL: str = "gpt-image-2"
    THUMBNAIL_MODEL: str = "gpt-image-2"
    YT_METADATA_MODEL: str = "gpt-5.6-luna"
    YT_METADATA_EFFORT: str = "low"
    # Hindi/Hinglish script narration (gpt-4o-mini-tts supports style instructions)
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "onyx"
    OPENAI_TTS_INSTRUCTIONS: str = (
        "Speak in natural Hindi for an Indian audience. "
        "Use a clear Hinglish delivery: Hindi sentence rhythm with English niche terms "
        "pronounced the way Indian creators say them. "
        "Calm, clear host tone — not rushed, not theatrical. "
        "Do not read stage directions or timing labels."
    )

    # SerpApi — Google Trends (web + YouTube) for topic scoring
    SERPAPI_API_KEY: str = ""
    TRENDS_GEO: str = "IN"
    TRENDS_LOCATION_NAME: str = "India"
    TRENDS_TTL_DAYS: int = 7

    # Instagram API with Instagram Login. Each client stores its own Instagram app id/secret.
    INSTAGRAM_GRAPH_VERSION: str = "v24.0"
    INSTAGRAM_REDIRECT_URI: str = "http://localhost:8000/social.instagram.callback"
    INSTAGRAM_OAUTH_SCOPES: str = (
        "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights"
    )

    FACEBOOK_REDIRECT_URI: str = "http://localhost:8000/social.facebook.callback"
    FACEBOOK_OAUTH_SCOPES: str = (
        "pages_manage_posts,pages_read_engagement,pages_show_list"
    )

    model_config = SettingsConfigDict(
        # Later dotenv files win among themselves; customise_sources makes dotenv beat OS env
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Prefer .env files over a stale shell OPENAI_API_KEY
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
