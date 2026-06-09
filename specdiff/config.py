"""Configuration management for spec-diff."""

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ExtractionConfig(BaseModel):
    """Configuration for text extraction."""

    top_margin: float = 0.08
    bottom_margin: float = 0.08
    repetition_threshold: int = 3


class SegmentationConfig(BaseModel):
    """Configuration for structural segmentation."""

    clause_patterns: list[str] = Field(
        default_factory=lambda: [
            r"^\d+(\.\d+)*\s+",
            r"^[A-Z]\.\d+(\.\d+)*\s+",
            r"^Annex\s+[A-Z]\b",
            r"^Table\s+\d+",
            r"^Figure\s+\d+",
        ]
    )


class DiffConfig(BaseModel):
    """Configuration for diff engine."""

    word_pattern: str = r"\w+|[^\w\s]"
    match_threshold: float = 0.5


class TablesConfig(BaseModel):
    """Configuration for table extraction."""

    enable_table_diff: bool = True
    table_confidence: float = 0.7


class FiguresConfig(BaseModel):
    """Configuration for figure detection."""

    text_density_threshold: float = 100.0
    image_count_change_threshold: int = 1


class APIConfig(BaseModel):
    """Configuration for API server."""

    max_file_size: int = 104857600
    job_retention: int = 86400
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )


class LLMConfig(BaseModel):
    """Configuration for optional LLM integration."""

    enable: bool = False
    model: str = "llama3.2:3b"
    base_url: str = "http://localhost:11434"
    timeout: int = 30


class LoggingConfig(BaseModel):
    """Configuration for logging."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Config(BaseSettings):
    """Main configuration object."""

    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    segmentation: SegmentationConfig = Field(default_factory=SegmentationConfig)
    diff: DiffConfig = Field(default_factory=DiffConfig)
    tables: TablesConfig = Field(default_factory=TablesConfig)
    figures: FiguresConfig = Field(default_factory=FiguresConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        """Load configuration from TOML file with env overrides."""
        config_dict: dict[str, Any] = {}

        if config_path is None:
            # Look for config.toml in current dir, then package dir
            if Path("config.toml").exists():
                config_path = Path("config.toml")
            else:
                package_config = Path(__file__).parent.parent / "config.toml"
                if package_config.exists():
                    config_path = package_config

        if config_path and config_path.exists():
            with open(config_path, "rb") as f:
                config_dict = tomllib.load(f)

        # Environment overrides
        if "SPECDIFF_LLM_ENABLE" in os.environ:
            if "llm" not in config_dict:
                config_dict["llm"] = {}
            config_dict["llm"]["enable"] = os.environ["SPECDIFF_LLM_ENABLE"].lower() == "true"

        if "SPECDIFF_LOG_LEVEL" in os.environ:
            if "logging" not in config_dict:
                config_dict["logging"] = {}
            config_dict["logging"]["level"] = os.environ["SPECDIFF_LOG_LEVEL"]

        return cls(**config_dict)

    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        logging.basicConfig(
            level=getattr(logging, self.logging.level.upper()),
            format=self.logging.format,
        )


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load()
        _config.setup_logging()
    return _config
