"""Registry for alerters."""

from detectk.base.alerter import BaseAlerter
from detectk.registry.base import ComponentRegistry


class AlerterRegistry(ComponentRegistry[BaseAlerter]):
    """Registry for alerter components.

    Example:
        >>> from detectk.base import BaseAlerter
        >>> from detectk.registry import AlerterRegistry
        >>>
        >>> @AlerterRegistry.register("mattermost")
        >>> class MattermostAlerter(BaseAlerter):
        ...     def __init__(self, config):
        ...         # implementation
        ...         pass
        >>>
        >>> # Later, in MetricCheck
        >>> alerter = AlerterRegistry.create("mattermost", config)
    """

    _components: dict[str, type[BaseAlerter]] = {}
    _registry_name = "alerter"
