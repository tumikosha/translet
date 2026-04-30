from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .llm import (
    AsyncLLMClient,
    AsyncOpenAICompatibleLLM,
    LLMClient,
    OpenAICompatibleLLM,
    aazure,
    agroq,
    anvidia,
    aopenai,
    azure,
    groq,
    nvidia,
    openai,
)
from .store import AsyncDbSetStore, AsyncRuleStore, DbSetStore, RuleStore
from .transjson import (
    AsyncTransJson,
    PipelineConfig,
    PromptBuilder,
    TransJson,
    make_async_deps,
    make_sync_deps,
)

OnFailure = Literal["raise", "regenerate"]
DEFAULT_DB_URL = "sqlite:///translet.db"


def load_dotenv(path: str | os.PathLike[str], *, override: bool = False) -> None:
    """Load a `.env`-style file into ``os.environ``.

    Format: ``KEY=VALUE`` per line, ``#`` comments, optional surrounding quotes.
    Missing files are silently ignored. By default existing env vars win
    (``setdefault`` semantics); pass ``override=True`` to force overwrite.
    """
    file_path = Path(path)
    if not file_path.exists():
        return
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


@dataclass(slots=True)
class TransletConfig:
    max_retries: int = 2
    on_failure: OnFailure = "regenerate"
    validate: bool = True
    ttl_seconds: int | None = None
    temperature: float = 0.0
    max_tokens: int = 2048
    system_prompt: str | None = None
    prompt_builder: PromptBuilder | None = field(default=None)
    sample_truncate_bytes: int = 2048

    def to_pipeline_config(self) -> PipelineConfig:
        return PipelineConfig(
            max_retries=self.max_retries,
            on_failure=self.on_failure,
            validate=self.validate,
            ttl_seconds=self.ttl_seconds,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            sample_truncate_bytes=self.sample_truncate_bytes,
        )

    def resolve_prompt_builder(self) -> PromptBuilder:
        if self.prompt_builder is not None:
            return self.prompt_builder
        return PromptBuilder(self.system_prompt)


class Translet:
    """Sync orchestrator: composes LLM client, rule store, and submodule facades."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        store: RuleStore,
        config: TransletConfig | None = None,
    ):
        self.llm = llm
        self.store = store
        self.config = config or TransletConfig()
        deps = make_sync_deps(
            llm=llm,
            store=store,
            config=self.config.to_pipeline_config(),
            prompt_builder=self.config.resolve_prompt_builder(),
        )
        self.transjson = TransJson(deps)

    @classmethod
    def from_env(
        cls,
        config: TransletConfig | None = None,
        *,
        env_file: str | os.PathLike[str] | None = None,
        override: bool = False,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        db_path: str | None = None,
        db_table: str | None = None,
        ttl_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> Translet:
        if env_file is not None:
            load_dotenv(env_file, override=override)
        _apply_env_overrides(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            db_path=db_path,
            db_table=db_table,
            ttl_seconds=ttl_seconds,
            max_retries=max_retries,
        )
        llm = _build_sync_llm_from_env()
        store = _build_sync_store_from_env()
        return cls(llm=llm, store=store, config=config or _config_from_env())


class AsyncTranslet:
    """Async orchestrator."""

    def __init__(
        self,
        *,
        llm: AsyncLLMClient,
        store: AsyncRuleStore,
        config: TransletConfig | None = None,
    ):
        self.llm = llm
        self.store = store
        self.config = config or TransletConfig()
        deps = make_async_deps(
            llm=llm,
            store=store,
            config=self.config.to_pipeline_config(),
            prompt_builder=self.config.resolve_prompt_builder(),
        )
        self.transjson = AsyncTransJson(deps)

    @classmethod
    async def from_env(
        cls,
        config: TransletConfig | None = None,
        *,
        env_file: str | os.PathLike[str] | None = None,
        override: bool = False,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        db_path: str | None = None,
        db_table: str | None = None,
        ttl_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> AsyncTranslet:
        """Build an :class:`AsyncTranslet` from environment variables.

        This is an async classmethod because ``dbset.async_connect`` is async.
        Use ``at = await AsyncTranslet.from_env()``.
        """
        if env_file is not None:
            load_dotenv(env_file, override=override)
        _apply_env_overrides(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            db_path=db_path,
            db_table=db_table,
            ttl_seconds=ttl_seconds,
            max_retries=max_retries,
        )
        llm = _build_async_llm_from_env()
        store = await _build_async_store_from_env()
        return cls(llm=llm, store=store, config=config or _config_from_env())


def _config_from_env() -> TransletConfig:
    cfg = TransletConfig()
    ttl = os.environ.get("TRANSLET_TTL_SECONDS")
    if ttl:
        cfg.ttl_seconds = int(ttl)
    retries = os.environ.get("TRANSLET_MAX_RETRIES")
    if retries:
        cfg.max_retries = int(retries)
    return cfg


def _provider_and_model_from_env() -> tuple[str, str, str | None]:
    provider = os.environ.get("TRANSLET_LLM_PROVIDER", "openai").lower()
    model = os.environ.get("TRANSLET_LLM_MODEL")
    if not model:
        raise RuntimeError(
            "TRANSLET_LLM_MODEL is required to construct an LLM client from environment."
        )
    base_url = os.environ.get("TRANSLET_LLM_BASE_URL")
    return provider, model, base_url


_PROVIDER_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
}


def _api_key_for(provider: str) -> str | None:
    """Provider-specific env var wins; TRANSLET_API_KEY is a generic fallback."""
    specific = _PROVIDER_KEY_ENV.get(provider)
    if specific and (value := os.environ.get(specific)):
        return value
    return os.environ.get("TRANSLET_API_KEY")


def _apply_env_overrides(
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    db_path: str | None = None,
    db_table: str | None = None,
    ttl_seconds: int | None = None,
    max_retries: int | None = None,
) -> None:
    """Force-write override values into ``os.environ`` (None means "keep as-is")."""
    if provider is not None:
        os.environ["TRANSLET_LLM_PROVIDER"] = provider
    if model is not None:
        os.environ["TRANSLET_LLM_MODEL"] = model
    if base_url is not None:
        os.environ["TRANSLET_LLM_BASE_URL"] = base_url
    if db_path is not None:
        os.environ["TRANSLET_DB_PATH"] = db_path
    if db_table is not None:
        os.environ["TRANSLET_DB_TABLE"] = db_table
    if ttl_seconds is not None:
        os.environ["TRANSLET_TTL_SECONDS"] = str(ttl_seconds)
    if max_retries is not None:
        os.environ["TRANSLET_MAX_RETRIES"] = str(max_retries)
    if api_key is not None:
        # Set provider-specific env var (it has priority in _api_key_for) so the
        # override actually wins over a key that may already be set in .env.
        eff_provider = os.environ.get("TRANSLET_LLM_PROVIDER", "openai").lower()
        env_var = _PROVIDER_KEY_ENV.get(eff_provider, "TRANSLET_API_KEY")
        os.environ[env_var] = api_key


def _build_sync_llm_from_env() -> OpenAICompatibleLLM:
    provider, model, base_url = _provider_and_model_from_env()
    api_key = _api_key_for(provider)
    if provider == "openai":
        return openai(model, api_key=api_key, base_url=base_url)
    if provider == "groq":
        return groq(model, api_key=api_key)
    if provider == "nvidia":
        return nvidia(model, api_key=api_key)
    if provider == "azure":
        return azure(model, api_key=api_key)
    raise ValueError(f"Unsupported provider in TRANSLET_LLM_PROVIDER: {provider!r}")


def _build_async_llm_from_env() -> AsyncOpenAICompatibleLLM:
    provider, model, base_url = _provider_and_model_from_env()
    api_key = _api_key_for(provider)
    if provider == "openai":
        return aopenai(model, api_key=api_key, base_url=base_url)
    if provider == "groq":
        return agroq(model, api_key=api_key)
    if provider == "nvidia":
        return anvidia(model, api_key=api_key)
    if provider == "azure":
        return aazure(model, api_key=api_key)
    raise ValueError(f"Unsupported provider in TRANSLET_LLM_PROVIDER: {provider!r}")


def _build_sync_store_from_env() -> DbSetStore:
    try:
        from dbset import connect
    except ImportError as exc:
        raise ImportError("dbset is required for the default Translet store.") from exc

    db_url = os.environ.get("TRANSLET_DB_PATH", DEFAULT_DB_URL)
    table = os.environ.get("TRANSLET_DB_TABLE", "translet_rules")
    db = connect(db_url)
    return DbSetStore(db, table=table)


async def _build_async_store_from_env() -> AsyncDbSetStore:
    try:
        from dbset import async_connect
    except ImportError as exc:
        raise ImportError("dbset is required for the default AsyncTranslet store.") from exc

    db_url = os.environ.get("TRANSLET_DB_PATH", DEFAULT_DB_URL)
    table = os.environ.get("TRANSLET_DB_TABLE", "translet_rules")
    db = await async_connect(db_url)
    return AsyncDbSetStore(db, table=table)
