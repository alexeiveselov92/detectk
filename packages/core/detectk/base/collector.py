"""Base class for data collectors.

All collectors must inherit from BaseCollector and implement the collect_bulk() method.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from detectk.models import DataPoint
from detectk.exceptions import CollectionError


class BaseCollector(ABC):
    """Abstract base class for all data collectors.

    Collectors are responsible for fetching time series data from data sources
    (databases, APIs, files, etc.). Each collector implementation handles
    connection management, query execution, and error handling for its specific
    data source.

    The collector returns a list of DataPoints for a given time period. The same
    method is used for both real-time collection (small time ranges like 10 minutes)
    and bulk historical loading (large time ranges like 30 days).

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
        ...     def collect_bulk(
        ...         self,
        ...         period_start: datetime,
        ...         period_finish: datetime,
        ...     ) -> list[DataPoint]:
        ...         # Execute query with period_start, period_finish variables
        ...         # Return list of data points with timestamps
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
    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        """Collect time series data for a period from data source.

        This method works for ANY time range:
        - Real-time: period_start="2024-11-02 14:00", period_finish="2024-11-02 14:10" → 1 point
        - Bulk load: period_start="2024-01-01", period_finish="2024-01-31" → 4,464 points

        The query should use Jinja2 variables {{ period_start }}, {{ period_finish }}, {{ interval }}
        and return multiple rows with timestamp and value columns.

        This method should:
        1. Connect to data source (use connection pooling)
        2. Execute query with period_start, period_finish template variables
        3. Parse ALL result rows into DataPoints
        4. Return list of DataPoints with timestamps and values

        Args:
            period_start: Start of time period (inclusive)
            period_finish: End of time period (exclusive)

        Returns:
            List of DataPoints with timestamps and values.
            Can be empty if no data in period.

        Raises:
            CollectionError: If collection fails due to:
                - Connection error
                - Query execution error
                - Invalid result format (missing timestamp or value columns)
                - Network timeout

        Example:
            >>> collector = ClickHouseCollector(config)
            >>>
            >>> # Real-time: collect last 10 minutes
            >>> points = collector.collect_bulk(
            ...     period_start=datetime(2024, 11, 2, 14, 0),
            ...     period_finish=datetime(2024, 11, 2, 14, 10),
            ... )
            >>> print(f"Collected {len(points)} points")
            Collected 1 points
            >>>
            >>> # Bulk load: collect 30 days
            >>> points = collector.collect_bulk(
            ...     period_start=datetime(2024, 1, 1),
            ...     period_finish=datetime(2024, 1, 31),
            ... )
            >>> print(f"Collected {len(points)} points")
            Collected 4464 points
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
