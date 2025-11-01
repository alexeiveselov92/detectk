"""Base registry implementation for component registration.

All specific registries (Collector, Detector, etc.) inherit from ComponentRegistry.
"""

from typing import Any, Callable, TypeVar, Generic
from detectk.exceptions import RegistryError

T = TypeVar("T")


class ComponentRegistry(Generic[T]):
    """Generic registry for component registration and lookup.

    Provides decorator-based registration and factory methods for creating
    component instances from configuration.

    This is the base class - use specific registries like CollectorRegistry,
    DetectorRegistry, etc.

    Example:
        >>> class CollectorRegistry(ComponentRegistry[BaseCollector]):
        ...     _registry_name = "collector"
        ...
        >>> @CollectorRegistry.register("clickhouse")
        >>> class ClickHouseCollector(BaseCollector):
        ...     pass
        >>>
        >>> # Later, create instance from config
        >>> collector = CollectorRegistry.create("clickhouse", config)
    """

    # Class-level storage for registered components
    # Each subclass gets its own _components dict
    _components: dict[str, type[T]] = {}
    _registry_name: str = "component"  # Override in subclasses

    @classmethod
    def register(cls, name: str) -> Callable[[type[T]], type[T]]:
        """Decorator for registering components.

        Args:
            name: Unique name for the component (used in YAML configs)

        Returns:
            Decorator function

        Raises:
            RegistryError: If component with this name already registered

        Example:
            >>> @CollectorRegistry.register("clickhouse")
            >>> class ClickHouseCollector(BaseCollector):
            ...     pass
        """

        def decorator(component_class: type[T]) -> type[T]:
            if name in cls._components:
                existing = cls._components[name]
                raise RegistryError(
                    f"{cls._registry_name.capitalize()} '{name}' already registered "
                    f"(existing: {existing.__module__}.{existing.__name__}, "
                    f"new: {component_class.__module__}.{component_class.__name__})",
                    component_type=cls._registry_name,
                    component_name=name,
                )

            cls._components[name] = component_class
            return component_class

        return decorator

    @classmethod
    def get(cls, name: str) -> type[T]:
        """Get registered component class by name.

        Args:
            name: Component name (from config)

        Returns:
            Component class

        Raises:
            RegistryError: If component not found

        Example:
            >>> collector_class = CollectorRegistry.get("clickhouse")
            >>> collector = collector_class(config)
        """
        if name not in cls._components:
            available = ", ".join(sorted(cls._components.keys()))
            raise RegistryError(
                f"{cls._registry_name.capitalize()} '{name}' not found. "
                f"Available: {available if available else 'none'}. "
                f"Make sure the package is installed (e.g., detectk-collectors-{name})",
                component_type=cls._registry_name,
                component_name=name,
            )

        return cls._components[name]

    @classmethod
    def create(cls, name: str, config: dict[str, Any]) -> T:
        """Create component instance from config.

        Factory method that looks up component class and instantiates it.

        Args:
            name: Component name (from config)
            config: Configuration dictionary

        Returns:
            Component instance

        Raises:
            RegistryError: If component not found
            ConfigurationError: If instantiation fails

        Example:
            >>> config = {"host": "localhost", "database": "analytics"}
            >>> collector = CollectorRegistry.create("clickhouse", config)
        """
        component_class = cls.get(name)

        try:
            return component_class(config)
        except Exception as e:
            raise RegistryError(
                f"Failed to create {cls._registry_name} '{name}': {e}",
                component_type=cls._registry_name,
                component_name=name,
            ) from e

    @classmethod
    def list_all(cls) -> list[str]:
        """List all registered component names.

        Returns:
            Sorted list of registered component names

        Example:
            >>> CollectorRegistry.list_all()
            ['clickhouse', 'http', 'sql']
        """
        return sorted(cls._components.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if component is registered.

        Args:
            name: Component name to check

        Returns:
            True if registered

        Example:
            >>> if CollectorRegistry.is_registered("clickhouse"):
            ...     print("ClickHouse collector available")
        """
        return name in cls._components

    @classmethod
    def clear(cls) -> None:
        """Clear all registered components.

        Primarily for testing - allows clean state between tests.

        Example:
            >>> CollectorRegistry.clear()
            >>> assert len(CollectorRegistry.list_all()) == 0
        """
        cls._components.clear()
