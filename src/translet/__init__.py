from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("translet")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

from . import llm, store, transjson
from .core import AsyncTranslet, Translet, TransletConfig, load_dotenv
from .stats import RuleStats, compute_stats, format_stats
from .exceptions import (
    ConversionError,
    JsonataError,
    RuleGenerationError,
    StoreError,
    TransletError,
    ValidationError,
)

__all__ = [
    "__version__",
    "Translet",
    "AsyncTranslet",
    "TransletConfig",
    "TransletError",
    "ConversionError",
    "RuleGenerationError",
    "StoreError",
    "ValidationError",
    "JsonataError",
    "load_dotenv",
    "RuleStats",
    "compute_stats",
    "format_stats",
    "llm",
    "store",
    "transjson",
]
