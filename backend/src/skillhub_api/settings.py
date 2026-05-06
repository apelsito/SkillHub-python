"""Application configuration.

Mirrors the Java Spring Boot ``application.yml`` using pydantic-settings. Env
var names are kept identical to the Java service so existing deployments can
reuse their secret stores.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _iso_duration(value: str) -> timedelta:
    """Parse an ISO-8601 duration like ``PT10M`` / ``PT8H`` / ``P30D``.

    Spring's `@DurationUnit` values arrive as strings from env. The frontend
    never sees these, so we parse a minimal subset: days, hours, minutes,
    seconds. Anything else raises.
    """
    if not value:
        return timedelta()
    if not value.startswith("P"):
        raise ValueError(f"invalid ISO duration: {value!r}")

    days = 0
    hours = 0
    minutes = 0
    seconds = 0
    remaining = value[1:]

    if "T" in remaining:
        date_part, time_part = remaining.split("T", 1)
    else:
        date_part, time_part = remaining, ""

    if date_part:
        if not date_part.endswith("D"):
            raise ValueError(f"invalid ISO duration date part: {value!r}")
        days = int(date_part[:-1])

    buf = ""
    for ch in time_part:
        if ch.isdigit():
            buf += ch
        elif ch == "H":
            hours = int(buf)
            buf = ""
        elif ch == "M":
            minutes = int(buf)
            buf = ""
        elif ch == "S":
            seconds = int(buf)
            buf = ""
        else:
            raise ValueError(f"unsupported ISO duration unit {ch!r} in {value!r}")

    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    # 127.0.0.1 — never `localhost`. On Windows, `localhost` resolves to
    # ::1 first and asyncpg fails with ConnectionRefusedError before
    # falling back to IPv4. Pinning IPv4 removes the failure mode.
    url: str = Field(
        default="postgresql+asyncpg://skillhub:skillhub_dev@127.0.0.1:5432/skillhub",
        alias="SPRING_DATASOURCE_URL",
    )
    username: str = Field(default="skillhub", alias="SPRING_DATASOURCE_USERNAME")
    password: SecretStr = Field(
        default=SecretStr("skillhub_dev"), alias="SPRING_DATASOURCE_PASSWORD"
    )
    pool_max_size: int = Field(default=10, alias="DB_POOL_MAX_SIZE")


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    # See DatabaseSettings.url — IPv4 only to avoid the Windows ::1 trap.
    host: str = Field(default="127.0.0.1", alias="REDIS_HOST")
    port: int = Field(default=6379, alias="REDIS_PORT")
    password: SecretStr = Field(default=SecretStr(""), alias="REDIS_PASSWORD")
    session_namespace: str = Field(default="skillhub:session", alias="SESSION_REDIS_NAMESPACE")


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    provider: str = Field(default="local", alias="SKILLHUB_STORAGE_PROVIDER")
    local_base_path: str = Field(default="/tmp/skillhub-storage", alias="STORAGE_BASE_PATH")
    s3_endpoint: str = Field(default="", alias="SKILLHUB_STORAGE_S3_ENDPOINT")
    s3_public_endpoint: str = Field(default="", alias="SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT")
    s3_bucket: str = Field(default="skillhub", alias="SKILLHUB_STORAGE_S3_BUCKET")
    s3_access_key: SecretStr = Field(default=SecretStr(""), alias="SKILLHUB_STORAGE_S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(default=SecretStr(""), alias="SKILLHUB_STORAGE_S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", alias="SKILLHUB_STORAGE_S3_REGION")
    s3_force_path_style: bool = Field(default=True, alias="SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE")
    s3_auto_create_bucket: bool = Field(
        default=False, alias="SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET"
    )
    s3_presign_expiry_raw: str = Field(default="PT10M", alias="SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY")

    @property
    def s3_presign_expiry(self) -> timedelta:
        return _iso_duration(self.s3_presign_expiry_raw)


class OAuthProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    github_client_id: str = Field(default="placeholder", alias="OAUTH2_GITHUB_CLIENT_ID")
    github_client_secret: SecretStr = Field(
        default=SecretStr("placeholder"), alias="OAUTH2_GITHUB_CLIENT_SECRET"
    )
    gitlab_client_id: str = Field(default="placeholder", alias="OAUTH2_GITLAB_CLIENT_ID")
    gitlab_client_secret: SecretStr = Field(
        default=SecretStr("placeholder"), alias="OAUTH2_GITLAB_CLIENT_SECRET"
    )
    gitlab_base_uri: str = Field(default="https://gitlab.com", alias="OAUTH2_GITLAB_BASE_URI")
    gitlab_display_name: str = Field(default="GitLab", alias="OAUTH2_GITLAB_DISPLAY_NAME")


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    mock_enabled: bool = Field(default=False, alias="SKILLHUB_AUTH_MOCK_ENABLED")
    direct_enabled: bool = Field(default=False, alias="SKILLHUB_AUTH_DIRECT_ENABLED")
    session_bootstrap_enabled: bool = Field(
        default=False, alias="SKILLHUB_AUTH_SESSION_BOOTSTRAP_ENABLED"
    )
    password_reset_code_expiry_raw: str = Field(
        default="PT10M", alias="SKILLHUB_AUTH_PASSWORD_RESET_CODE_EXPIRY"
    )
    password_reset_from_address: str = Field(
        default="noreply@skillhub.local", alias="SKILLHUB_AUTH_PASSWORD_RESET_FROM_ADDRESS"
    )
    password_reset_from_name: str = Field(
        default="SkillHub", alias="SKILLHUB_AUTH_PASSWORD_RESET_FROM_NAME"
    )

    @property
    def password_reset_code_expiry(self) -> timedelta:
        return _iso_duration(self.password_reset_code_expiry_raw)


class SearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    engine: str = Field(default="postgres", alias="SKILLHUB_SEARCH_ENGINE")
    rebuild_on_startup: bool = Field(default=False, alias="SKILLHUB_SEARCH_REBUILD_ON_STARTUP")
    semantic_enabled: bool = Field(default=True, alias="SKILLHUB_SEARCH_SEMANTIC_ENABLED")
    semantic_weight: float = Field(default=0.35, alias="SKILLHUB_SEARCH_SEMANTIC_WEIGHT")
    semantic_candidate_multiplier: int = Field(
        default=8, alias="SKILLHUB_SEARCH_SEMANTIC_CANDIDATE_MULTIPLIER"
    )
    semantic_max_candidates: int = Field(
        default=120, alias="SKILLHUB_SEARCH_SEMANTIC_MAX_CANDIDATES"
    )


class PublishLimits(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    # Matches SkillPackagePolicy.java:18 (MAX_FILE_COUNT = 500).
    max_file_count: int = Field(default=500, alias="SKILLHUB_PUBLISH_MAX_FILE_COUNT")
    max_single_file_size: int = Field(
        default=10 * 1024 * 1024, alias="SKILLHUB_PUBLISH_MAX_SINGLE_FILE_SIZE"
    )
    max_package_size: int = Field(
        default=100 * 1024 * 1024, alias="SKILLHUB_PUBLISH_MAX_PACKAGE_SIZE"
    )


class ScannerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    enabled: bool = Field(default=False, alias="SKILLHUB_SECURITY_SCANNER_ENABLED")
    base_url: str = Field(default="http://127.0.0.1:8000", alias="SKILLHUB_SECURITY_SCANNER_URL")
    mode: str = Field(default="local", alias="SKILLHUB_SECURITY_SCANNER_MODE")
    connect_timeout_ms: int = Field(default=5000, alias="SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT")
    read_timeout_ms: int = Field(default=300_000, alias="SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT")
    retry_max_attempts: int = Field(default=3, alias="SKILLHUB_SECURITY_SCANNER_RETRY_MAX")


class ScanStreamSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    key: str = Field(default="skillhub:scan:requests", alias="SKILLHUB_SCAN_STREAM_KEY")
    group: str = Field(default="skillhub-scanners", alias="SKILLHUB_SCAN_STREAM_GROUP")
    reclaim_enabled: bool = Field(default=True, alias="SKILLHUB_SCAN_STREAM_RECLAIM_ENABLED")
    reclaim_min_idle_raw: str = Field(default="PT2M", alias="SKILLHUB_SCAN_STREAM_RECLAIM_MIN_IDLE")
    reclaim_batch_size: int = Field(default=20, alias="SKILLHUB_SCAN_STREAM_RECLAIM_BATCH_SIZE")
    reclaim_interval_raw: str = Field(
        default="PT30S", alias="SKILLHUB_SCAN_STREAM_RECLAIM_INTERVAL"
    )

    @property
    def reclaim_min_idle(self) -> timedelta:
        return _iso_duration(self.reclaim_min_idle_raw)

    @property
    def reclaim_interval(self) -> timedelta:
        return _iso_duration(self.reclaim_interval_raw)


class BootstrapAdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", env_file=".env", env_file_encoding="utf-8")

    enabled: bool = Field(default=False, alias="BOOTSTRAP_ADMIN_ENABLED")
    user_id: str = Field(default="docker-admin", alias="BOOTSTRAP_ADMIN_USER_ID")
    username: str = Field(default="admin", alias="BOOTSTRAP_ADMIN_USERNAME")
    password: SecretStr = Field(
        default=SecretStr("ChangeMe!2026"), alias="BOOTSTRAP_ADMIN_PASSWORD"
    )
    display_name: str = Field(default="Admin", alias="BOOTSTRAP_ADMIN_DISPLAY_NAME")
    email: str = Field(default="admin@skillhub.local", alias="BOOTSTRAP_ADMIN_EMAIL")


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="skillhub", alias="SKILLHUB_APP_NAME")
    public_base_url: str = Field(default="", alias="SKILLHUB_PUBLIC_BASE_URL")
    access_policy_mode: str = Field(default="OPEN", alias="SKILLHUB_ACCESS_POLICY_MODE")
    server_port: int = Field(default=8080, alias="SERVER_PORT")
    session_timeout_raw: str = Field(default="PT8H", alias="SERVER_SERVLET_SESSION_TIMEOUT")
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    oauth: OAuthProviderSettings = Field(default_factory=OAuthProviderSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    publish: PublishLimits = Field(default_factory=PublishLimits)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    scan_stream: ScanStreamSettings = Field(default_factory=ScanStreamSettings)
    bootstrap_admin: BootstrapAdminSettings = Field(default_factory=BootstrapAdminSettings)

    label_max_definitions: int = Field(default=100, alias="SKILLHUB_LABEL_MAX_DEFINITIONS")
    label_max_per_skill: int = Field(default=10, alias="SKILLHUB_LABEL_MAX_PER_SKILL")

    download_anon_cookie_name: str = Field(
        default="skillhub_anon_dl", alias="SKILLHUB_DOWNLOAD_ANON_COOKIE_NAME"
    )
    download_anon_cookie_max_age_raw: str = Field(
        default="P30D", alias="SKILLHUB_DOWNLOAD_ANON_COOKIE_MAX_AGE"
    )
    download_anon_cookie_secret: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        alias="SKILLHUB_DOWNLOAD_ANON_COOKIE_SECRET",
    )

    profile_machine_review_enabled: bool = Field(
        default=True, alias="SKILLHUB_PROFILE_MACHINE_REVIEW_ENABLED"
    )
    profile_human_review_enabled: bool = Field(
        default=True, alias="SKILLHUB_PROFILE_HUMAN_REVIEW_ENABLED"
    )

    @property
    def session_timeout(self) -> timedelta:
        return _iso_duration(self.session_timeout_raw)

    @property
    def download_anon_cookie_max_age(self) -> timedelta:
        return _iso_duration(self.download_anon_cookie_max_age_raw)

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
