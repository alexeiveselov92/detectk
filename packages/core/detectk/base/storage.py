"""Base class for metric storage.

Storage is used to persist metric history for detection algorithms that need
historical windows.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
import pandas as pd

from detectk.models import DataPoint
from detectk.exceptions import StorageError


class BaseStorage(ABC):
    """Abstract base class for metric history storage.

    Storage implementations persist metric data points over time, allowing
    detectors to read historical windows (e.g., last 30 days) for anomaly
    detection. Storage is optional - not all deployments need it.

    The storage interface is intentionally simple:
    - save(): Write single data point
    - query(): Read historical window
    - delete(): Clean up old data (retention management)

    Example Implementation:
        >>> from detectk.base import BaseStorage
        >>> from detectk.registry import StorageRegistry
        >>>
        >>> @StorageRegistry.register("clickhouse")
        >>> class ClickHouseStorage(BaseStorage):
        ...     def __init__(self, config: dict[str, Any]) -> None:
        ...         self.config = config
        ...         self.validate_config(config)
        ...
        ...     def save(self, metric_name: str, datapoint: DataPoint) -> None:
        ...         # Insert into metrics_history table
        ...         pass
        ...
        ...     def query(self, metric_name: str, window: str | int,
        ...               end_time: datetime | None = None) -> pd.DataFrame:
        ...         # Query historical data
        ...         pass
    """

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize storage with configuration.

        Args:
            config: Storage configuration from YAML
                   Contains connection string, table name, etc.

        Raises:
            ConfigurationError: If config is invalid
        """
        pass

    @abstractmethod
    def save(self, metric_name: str, datapoint: DataPoint) -> None:
        """Save single data point to storage.

        This method should:
        1. Connect to storage (use connection pooling)
        2. Insert data point into metrics_history table
        3. Handle errors gracefully (retry if transient)

        Args:
            metric_name: Name of metric (for partitioning/indexing)
            datapoint: Data point to save

        Raises:
            StorageError: If save operation fails

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> point = DataPoint(
            ...     timestamp=datetime.now(),
            ...     value=1234.5,
            ...     metadata={"source": "clickhouse"}
            ... )
            >>> storage.save("sessions_10min", point)
        """
        pass

    @abstractmethod
    def query(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Query historical data for metric.

        This method should:
        1. Parse window parameter ("30 days" or number of points)
        2. Calculate time range based on end_time
        3. Query storage with proper indexes
        4. Return DataFrame with required columns

        Args:
            metric_name: Name of metric to query
            window: Size of historical window
                   String: "30 days", "7 days", "24 hours"
                   Int: Number of most recent data points
            end_time: End of time window (default: now())
                     For backtesting, pass historical time

        Returns:
            DataFrame with columns: timestamp, value, metadata
            Sorted by timestamp ascending (oldest first)
            Empty DataFrame if no data found

        Raises:
            StorageError: If query fails
            ValueError: If window format invalid

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> # Get last 30 days of data
            >>> df = storage.query("sessions_10min", "30 days")
            >>> print(df.shape)
            (4320, 3)  # 30 days * 24 hours * 6 (10-min intervals)
            >>>
            >>> # Get last 100 data points
            >>> df = storage.query("sessions_10min", 100)
            >>> print(df.shape)
            (100, 3)
            >>>
            >>> # Backtesting: query historical window
            >>> df = storage.query(
            ...     "sessions_10min",
            ...     "30 days",
            ...     end_time=datetime(2024, 1, 1)
            ... )
        """
        pass

    @abstractmethod
    def delete(
        self,
        metric_name: str,
        older_than: datetime,
    ) -> int:
        """Delete old data for retention management.

        This method should:
        1. Delete all data points older than specified time
        2. Return number of rows deleted
        3. Handle partitioned tables efficiently

        Args:
            metric_name: Name of metric to clean up
            older_than: Delete data older than this timestamp

        Returns:
            Number of rows deleted

        Raises:
            StorageError: If deletion fails

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> # Delete data older than 90 days
            >>> retention_date = datetime.now() - timedelta(days=90)
            >>> deleted = storage.delete("sessions_10min", retention_date)
            >>> print(f"Deleted {deleted} old data points")
        """
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate storage-specific configuration.

        Should check:
        - Connection string present and valid
        - Table name specified
        - Retention days valid (if specified)

        Args:
            config: Configuration dictionary to validate

        Raises:
            ConfigurationError: If config is invalid
        """
        pass

    def table_exists(self, table_name: str) -> bool:
        """Check if table exists in storage.

        Optional helper method for storage implementations.

        Args:
            table_name: Name of table to check

        Returns:
            True if table exists

        Raises:
            StorageError: If check fails
        """
        raise NotImplementedError("table_exists() not implemented for this storage")

    def create_table(self, table_name: str, schema: dict[str, str]) -> None:
        """Create table in storage with specified schema.

        Optional helper method for storage implementations.

        Args:
            table_name: Name of table to create
            schema: Column definitions (name -> type)

        Raises:
            StorageError: If creation fails
        """
        raise NotImplementedError("create_table() not implemented for this storage")

    def close(self) -> None:
        """Close connections and clean up resources.

        Optional method for cleanup.
        """
        pass
