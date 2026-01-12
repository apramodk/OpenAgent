"""Configuration management."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import tomllib


@dataclass
class LLMConfig:
    """LLM configuration."""

    provider: str = "azure"
    model: str = "gpt-4.1"
    endpoint: str = ""
    api_key: str = ""
    max_tokens: int = 16384  # GPT-4.1 supports up to 32K output
    temperature: float = 0.7


@dataclass
class TokenConfig:
    """Token tracking configuration."""

    budget: int | None = None
    warn_at: int = 80  # Warn at this percentage


@dataclass
class SessionConfig:
    """Session configuration."""

    db_path: Path = field(default_factory=lambda: Path.home() / ".local/share/openagent/sessions.db")
    auto_save: bool = True


@dataclass
class RAGConfig:
    """RAG configuration."""

    db_path: Path = field(default_factory=lambda: Path.home() / ".local/share/openagent/chroma")
    collection: str = "codebase_specs"


@dataclass
class TUIConfig:
    """TUI configuration."""

    theme: str = "dark"
    show_file_tree: bool = False
    vim_mode: bool = True
    keybindings: dict = field(default_factory=dict)


@dataclass
class Config:
    """Main configuration container."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    tokens: TokenConfig = field(default_factory=TokenConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    tui: TUIConfig = field(default_factory=TUIConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        """
        Load configuration from file and environment.

        Priority (highest to lowest):
        1. Environment variables
        2. Config file
        3. Defaults
        """
        from dotenv import load_dotenv
        load_dotenv()

        config = cls()

        # Try to load from file
        if path is None:
            path = os.environ.get(
                "OPENAGENT_CONFIG",
                Path.home() / ".config/openagent/config.toml",
            )

        config_path = Path(path)
        if config_path.exists():
            config = cls._load_from_toml(config_path)

        # Override with environment variables
        config = cls._apply_env_overrides(config)

        return config

    @classmethod
    def _load_from_toml(cls, path: Path) -> "Config":
        """Load config from TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls(
            llm=cls._parse_llm_config(data.get("llm", {})),
            tokens=cls._parse_token_config(data.get("tokens", {})),
            session=cls._parse_session_config(data.get("session", {})),
            rag=cls._parse_rag_config(data.get("rag", {})),
            tui=cls._parse_tui_config(data.get("tui", {})),
        )

    @classmethod
    def _parse_llm_config(cls, data: dict) -> LLMConfig:
        return LLMConfig(
            provider=data.get("provider", "azure"),
            model=data.get("model", "gpt-4.1"),
            endpoint=cls._expand_env(data.get("endpoint", "")),
            api_key=cls._expand_env(data.get("api_key", "")),
            max_tokens=data.get("max_tokens", 16384),
            temperature=data.get("temperature", 0.7),
        )

    @classmethod
    def _parse_token_config(cls, data: dict) -> TokenConfig:
        return TokenConfig(
            budget=data.get("budget"),
            warn_at=data.get("warn_at", 80),
        )

    @classmethod
    def _parse_session_config(cls, data: dict) -> SessionConfig:
        db_path = data.get("db_path", "~/.local/share/openagent/sessions.db")
        return SessionConfig(
            db_path=Path(db_path).expanduser(),
            auto_save=data.get("auto_save", True),
        )

    @classmethod
    def _parse_rag_config(cls, data: dict) -> RAGConfig:
        db_path = data.get("db_path", "~/.local/share/openagent/chroma")
        return RAGConfig(
            db_path=Path(db_path).expanduser(),
            collection=data.get("collection", "codebase_specs"),
        )

    @classmethod
    def _parse_tui_config(cls, data: dict) -> TUIConfig:
        return TUIConfig(
            theme=data.get("theme", "dark"),
            show_file_tree=data.get("show_file_tree", False),
            vim_mode=data.get("vim_mode", True),
            keybindings=data.get("keybindings", {}),
        )

    @classmethod
    def _apply_env_overrides(cls, config: "Config") -> "Config":
        """Apply environment variable overrides."""
        # LLM config
        if oai_endpoint := os.environ.get("PROJECT_ENDPOINT_OAI"):
            parts = oai_endpoint.split("/openai/")
            if parts:
                config.llm.endpoint = parts[0]

        if endpoint := os.environ.get("PROJECT_ENDPOINT"):
            config.llm.endpoint = endpoint
        if endpoint := os.environ.get("AZURE_OPENAI_ENDPOINT"):
            config.llm.endpoint = endpoint
        
        if key := os.environ.get("AZURE_KEY"):
            config.llm.api_key = key
        if key := os.environ.get("AZURE_OPENAI_KEY"):
            config.llm.api_key = key
            
        if model := os.environ.get("MODEL_DEPLOYMENT_NAME"):
            config.llm.model = model

        # Session config
        if db_path := os.environ.get("OPENAGENT_SESSION_DB"):
            config.session.db_path = Path(db_path).expanduser()

        return config

    @staticmethod
    def _expand_env(value: str) -> str:
        """Expand environment variables in string (${VAR} format)."""
        if not value:
            return value

        import re
        pattern = r"\$\{(\w+)\}"

        def replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return re.sub(pattern, replace, value)
