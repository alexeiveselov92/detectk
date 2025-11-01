"""Registry for anomaly detectors."""

from detectk.base.detector import BaseDetector
from detectk.registry.base import ComponentRegistry


class DetectorRegistry(ComponentRegistry[BaseDetector]):
    """Registry for detector components.

    Note: Detectors require storage parameter in addition to config.

    Example:
        >>> from detectk.base import BaseDetector
        >>> from detectk.registry import DetectorRegistry
        >>>
        >>> @DetectorRegistry.register("mad")
        >>> class MADDetector(BaseDetector):
        ...     def __init__(self, storage, **params):
        ...         super().__init__(storage, **params)
        ...         # implementation
        >>>
        >>> # Later, in MetricCheck
        >>> detector_class = DetectorRegistry.get("mad")
        >>> detector = detector_class(storage, **detector_params)
    """

    _components: dict[str, type[BaseDetector]] = {}
    _registry_name = "detector"
