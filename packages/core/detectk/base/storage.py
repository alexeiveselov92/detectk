"""Base class for metric storage.

Storage is used to persist:
1. Collected metric datapoints (dtk_datapoints table - required)
2. Detection results (dtk_detections table - optional)
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
import pandas as pd

from detectk.models import DataPoint, DetectionResult
from detectk.exceptions import StorageError


class BaseStorage(ABC):
    """Abstract base class for metric storage.

    Storage implementations persist data in two tables:
    1. dtk_datapoints - Collected metric values (required for detection)
    2. dtk_detections - Detection results (optional, for audit/cooldown)

    The storage interface separates datapoints and detections:
    - save_datapoint() / query_datapoints() - For collected values
    - save_detection() / query_detections() - For detection results
    - cleanup_old_data() - Retention management for both tables

    Example Implementation:
        >>> from detectk.base import BaseStorage
        >>> from detectk.registry import StorageRegistry
        >>>
        >>> @StorageRegistry.register("clickhouse")
        >>> class ClickHouseStorage(BaseStorage):
        ...     def __init__(self, config: dict[str, Any]) -> None:
        ...         self.config = config
        ...         self.validate_config(config)
        ...         self._ensure_tables_exist()
        ...
        ...     def save_datapoint(self, metric_name: str, datapoint: DataPoint) -> None:
        ...         # Insert into dtk_datapoints table
        ...         pass
        ...
        ...     def query_datapoints(self, metric_name: str, window: str | int,
        ...                         end_time: datetime | None = None) -> pd.DataFrame:
        ...         # Query historical datapoints
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

    # ========================================================================
    # Datapoints (dtk_datapoints table) - Required for detection
    # ========================================================================

    @abstractmethod
    def save_datapoint(self, metric_name: str, datapoint: DataPoint) -> None:
        """Save collected metric value to dtk_datapoints table.

        This method should:
        1. Connect to storage (use connection pooling)
        2. Insert datapoint into dtk_datapoints table
        3. Handle errors gracefully (retry if transient)

        Args:
            metric_name: Name of metric (indexed for fast queries)
            datapoint: Data point with timestamp, value, and optional context

        Raises:
            StorageError: If save operation fails

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> point = DataPoint(
            ...     timestamp=datetime.now(),
            ...     value=1234.5,
            ...     metadata={"hour_of_day": 14, "day_of_week": "monday"}
            ... )
            >>> storage.save_datapoint("sessions_10min", point)
        """
        pass

    @abstractmethod
    def query_datapoints(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Query historical datapoints from dtk_datapoints table.

        This method should:
        1. Parse window parameter ("30 days" or number of points)
        2. Calculate time range based on end_time
        3. Query dtk_datapoints with proper indexes
        4. Return DataFrame with required columns

        Args:
            metric_name: Name of metric to query
            window: Size of historical window
                   String: "30 days", "7 days", "24 hours"
                   Int: Number of most recent data points
            end_time: End of time window (default: now())
                     For backtesting, pass historical time

        Returns:
            DataFrame with columns: timestamp, value, context (JSONB)
            Sorted by timestamp ascending (oldest first)
            Empty DataFrame if no data found

        Raises:
            StorageError: If query fails
            ValueError: If window format invalid

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> # Get last 30 days of data
            >>> df = storage.query_datapoints("sessions_10min", "30 days")
            >>> print(df.shape)
            (4320, 3)  # 30 days * 24 hours * 6 (10-min intervals)
            >>>
            >>> # Get last 100 data points
            >>> df = storage.query_datapoints("sessions_10min", 100)
            >>> print(df.shape)
            (100, 3)
            >>>
            >>> # Backtesting: query historical window
            >>> df = storage.query_datapoints(
            ...     "sessions_10min",
            ...     "30 days",
            ...     end_time=datetime(2024, 1, 1)
            ... )
        """
        pass

    # ========================================================================
    # Detections (dtk_detections table) - Optional for audit/cooldown
    # ========================================================================

    @abstractmethod
    def save_detection(
        self,
        metric_name: str,
        detection: DetectionResult,
        alert_sent: bool = False,
        alert_reason: str | None = None,
        alerter_type: str | None = None,
    ) -> None:
        """Save detection result to dtk_detections table (if enabled).

        This method should only save if storage config has save_detections=true.

        Args:
            metric_name: Name of metric
            detection: Detection result with anomaly status and bounds
            alert_sent: Whether alert was sent for this detection
            alert_reason: Reason for alert (if sent)
            alerter_type: Type of alerter used (e.g., "mattermost")

        Raises:
            StorageError: If save operation fails

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> result = DetectionResult(
            ...     metric_name="sessions_10min",
            ...     timestamp=datetime.now(),
            ...     value=1500.0,
            ...     is_anomaly=True,
            ...     score=4.2,
            ...     lower_bound=1000.0,
            ...     upper_bound=1200.0,
            ... )
            >>> storage.save_detection(
            ...     "sessions_10min",
            ...     result,
            ...     alert_sent=True,
            ...     alert_reason="Anomaly detected: score=4.2"
            ... )
        """
        pass

    @abstractmethod
    def query_detections(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
        anomalies_only: bool = False,
    ) -> pd.DataFrame:
        """Query historical detections from dtk_detections table.

        Useful for:
        - Cooldown logic (when was last alert sent?)
        - Analysis of false positives/negatives
        - Dashboard visualization

        Args:
            metric_name: Name of metric to query
            window: Size of historical window (same format as query_datapoints)
            end_time: End of time window (default: now())
            anomalies_only: If True, only return rows where is_anomaly=true

        Returns:
            DataFrame with columns: timestamp, value, is_anomaly, score,
                                   bounds, alert_sent, etc.
            Sorted by timestamp ascending
            Empty DataFrame if no data found

        Raises:
            StorageError: If query fails

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> # Check if we alerted in last 60 minutes (cooldown)
            >>> recent = storage.query_detections(
            ...     "sessions_10min",
            ...     "60 minutes",
            ...     anomalies_only=True
            ... )
            >>> if recent[recent['alert_sent']].shape[0] > 0:
            ...     print("Alert sent recently, skip")
        """
        pass

    # ========================================================================
    # Retention management
    # ========================================================================

    @abstractmethod
    def cleanup_old_data(
        self,
        datapoints_retention_days: int,
        detections_retention_days: int | None = None,
    ) -> tuple[int, int]:
        """Delete old data based on retention policies.

        This method should:
        1. Delete datapoints older than datapoints_retention_days
        2. Delete detections older than detections_retention_days (if specified)
        3. Handle partitioned tables efficiently (e.g., DROP PARTITION in ClickHouse)

        Args:
            datapoints_retention_days: Keep datapoints for N days
            detections_retention_days: Keep detections for N days (None = keep forever)

        Returns:
            Tuple of (datapoints_deleted, detections_deleted)

        Raises:
            StorageError: If deletion fails

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> # Keep 90 days of datapoints, 30 days of detections
            >>> dp_deleted, det_deleted = storage.cleanup_old_data(
            ...     datapoints_retention_days=90,
            ...     detections_retention_days=30
            ... )
            >>> print(f"Cleaned up {dp_deleted} datapoints, {det_deleted} detections")
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
