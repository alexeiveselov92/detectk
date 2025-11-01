"""Base class for data collectors.

All collectors must inherit from BaseCollector and implement the collect() method.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from detectk.models import DataPoint
from detectk.exceptions import CollectionError


class BaseCollector(ABC):
    """Abstract base class for all data collectors.

    Collectors are responsible for fetching current metric values from data sources
    (databases, APIs, files, etc.). Each collector implementation handles
    connection management, query execution, and error handling for its specific
    data source.

    The collector returns a single DataPoint (not a DataFrame) representing the
    current value at the specified time. This keeps queries lightweight and
    avoids loading large amounts of data from source systems.

    Example Implementation:
        >>> from detectk.base import BaseCollector
        >>> from detectk.registry import CollectorRegistry
        >>>
        >>> @CollectorRegistry.register("clickhouse")
        >>> class ClickHouseCollector(BaseCollector):
        ...     def __init__(self, config: dict[str, Any]) -> None:
        ...         self.config = config
        ...         self.validate_config(config)
        ...
        ...     def collect(self, at_time: datetime | None = None) -> DataPoint:
        ...         # Execute query against ClickHouse
        ...         # Return single data point
        ...         pass
        ...
        ...     def validate_config(self, config: dict[str, Any]) -> None:
        ...         # Validate connection string, query, etc.
        ...         pass
    """

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize collector with configuration.

        Args:
            config: Collector configuration from YAML
                   Contains connection params, query, etc.

        Raises:
            ConfigurationError: If config is invalid
        """
        pass

    @abstractmethod
    def collect(self, at_time: datetime | None = None) -> DataPoint:
        """Collect current metric value from data source.

        This method should:
        1. Connect to data source (use connection pooling)
        2. Execute query with at_time parameter (for backtesting)
        3. Parse result into single value
        4. Return DataPoint with timestamp and value

        Args:
            at_time: Time to collect data for (default: now())
                    Used for backtesting and scheduled runs.
                    Should be passed to query as template variable.

        Returns:
            DataPoint with timestamp and value

        Raises:
            CollectionError: If collection fails due to:
                - Connection error
                - Query execution error
                - Invalid result format
                - Network timeout

        Example:
            >>> collector = ClickHouseCollector(config)
            >>> point = collector.collect()
            >>> print(f"Value: {point.value} at {point.timestamp}")
            Value: 1234.5 at 2024-11-01 15:30:00

            >>> # Backtesting: collect historical value
            >>> past_point = collector.collect(at_time=datetime(2024, 1, 1))
        """
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate collector-specific configuration.

        Should check:
        - Required fields present (host, database, query, etc.)
        - Connection string format valid
        - Query is not empty
        - Environment variables resolved

        Args:
            config: Configuration dictionary to validate

        Raises:
            ConfigurationError: If config is invalid with specific error message
        """
        pass

    def close(self) -> None:
        """Close connections and clean up resources.

        Optional method for collectors that maintain persistent connections.
        Called when MetricCheck is done or in context manager __exit__.

        Default implementation does nothing.
        """
        pass
