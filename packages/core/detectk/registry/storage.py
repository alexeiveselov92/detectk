"""Registry for storage implementations."""

from detectk.base.storage import BaseStorage
from detectk.registry.base import ComponentRegistry


class StorageRegistry(ComponentRegistry[BaseStorage]):
    """Registry for storage components.

    Example:
        >>> from detectk.base import BaseStorage
        >>> from detectk.registry import StorageRegistry
        >>>
        >>> @StorageRegistry.register("clickhouse")
        >>> class ClickHouseStorage(BaseStorage):
        ...     def __init__(self, config):
        ...         # implementation
        ...         pass
        >>>
        >>> # Later, in MetricCheck
        >>> storage = StorageRegistry.create("clickhouse", config)
    """

    _components: dict[str, type[BaseStorage]] = {}
    _registry_name = "storage"
