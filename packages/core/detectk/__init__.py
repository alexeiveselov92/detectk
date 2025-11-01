"""DetectK - Flexible metric monitoring and anomaly detection framework.

This package provides the core functionality for:
- Collecting metrics from various data sources
- Detecting anomalies using configurable algorithms
- Sending alerts through multiple channels
- Backtesting detection algorithms on historical data

For more information, see: https://github.com/alexeiveselov92/detectk
"""

__version__ = "0.1.0"

# Core exceptions
from detectk.exceptions import (
    DetectKError,
    ConfigurationError,
    CollectionError,
    DetectionError,
    StorageError,
    AlertError,
    RegistryError,
)

# Data models
from detectk.models import (
    DataPoint,
    DetectionResult,
    CheckResult,
    AlertConditions,
)

# Base classes
from detectk.base import (
    BaseCollector,
    BaseDetector,
    BaseAlerter,
    BaseStorage,
)

# Registry
from detectk.registry import (
    CollectorRegistry,
    DetectorRegistry,
    AlerterRegistry,
    StorageRegistry,
)

# Configuration
from detectk.config import ConfigLoader, MetricConfig

# Main orchestrator
from detectk.check import MetricCheck

__all__ = [
    # Version
    "__version__",
    # Exceptions
    "DetectKError",
    "ConfigurationError",
    "CollectionError",
    "DetectionError",
    "StorageError",
    "AlertError",
    "RegistryError",
    # Data models
    "DataPoint",
    "DetectionResult",
    "CheckResult",
    "AlertConditions",
    # Base classes
    "BaseCollector",
    "BaseDetector",
    "BaseAlerter",
    "BaseStorage",
    # Registries
    "CollectorRegistry",
    "DetectorRegistry",
    "AlerterRegistry",
    "StorageRegistry",
    # Configuration
    "ConfigLoader",
    "MetricConfig",
    # Main orchestrator
    "MetricCheck",
]
