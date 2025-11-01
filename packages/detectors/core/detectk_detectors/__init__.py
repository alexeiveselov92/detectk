"""Core detectors for DetectK."""

__version__ = "0.1.0"

# Import detectors for auto-registration
from detectk_detectors.threshold import ThresholdDetector

__all__ = [
    "__version__",
    "ThresholdDetector",
]
