"""Component registry for dynamic discovery and instantiation.

The registry pattern enables plugin architecture - new collectors, detectors,
and alerters can be added without modifying core code.
"""

from detectk.registry.base import ComponentRegistry
from detectk.registry.collector import CollectorRegistry
from detectk.registry.detector import DetectorRegistry
from detectk.registry.alerter import AlerterRegistry
from detectk.registry.storage import StorageRegistry

__all__ = [
    "ComponentRegistry",
    "CollectorRegistry",
    "DetectorRegistry",
    "AlerterRegistry",
    "StorageRegistry",
]
