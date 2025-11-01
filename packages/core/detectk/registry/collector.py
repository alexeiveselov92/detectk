"""Registry for data collectors."""

from detectk.base.collector import BaseCollector
from detectk.registry.base import ComponentRegistry


class CollectorRegistry(ComponentRegistry[BaseCollector]):
    """Registry for collector components.

    Example:
        >>> from detectk.base import BaseCollector
        >>> from detectk.registry import CollectorRegistry
        >>>
        >>> @CollectorRegistry.register("clickhouse")
        >>> class ClickHouseCollector(BaseCollector):
        ...     def __init__(self, config):
        ...         # implementation
        ...         pass
        >>>
        >>> # Later, in MetricCheck
        >>> collector = CollectorRegistry.create("clickhouse", config)
    """

    _components: dict[str, type[BaseCollector]] = {}
    _registry_name = "collector"
