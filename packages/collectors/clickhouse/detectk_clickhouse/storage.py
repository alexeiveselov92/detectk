"""ClickHouse storage for DetectK metric history."""

import logging
import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError

from detectk.base import BaseStorage
from detectk.models import DataPoint, DetectionResult
from detectk.exceptions import StorageError, ConfigurationError
from detectk.registry import StorageRegistry

logger = logging.getLogger(__name__)


@StorageRegistry.register("clickhouse")
class ClickHouseStorage(BaseStorage):
    """Storage backend for ClickHouse database.

    Manages two tables:
    1. dtk_datapoints - collected metric values (required for detection)
    2. dtk_detections - detection results (optional, for audit/cooldown)

    Configuration:
        host: ClickHouse server host (default: localhost)
        port: ClickHouse server port (default: 9000)
        database: Database name (default: default)
        user: Username (optional)
        password: Password (optional)
        timeout: Query timeout in seconds (default: 30)
        secure: Use SSL connection (default: False)
        save_detections: Save detection results to dtk_detections (default: False)

    Example:
        >>> from detectk_clickhouse import ClickHouseStorage
        >>> from detectk.models import DataPoint
        >>> from datetime import datetime
        >>>
        >>> config = {
        ...     "host": "localhost",
        ...     "database": "default",
        ... }
        >>> storage = ClickHouseStorage(config)
        >>>
        >>> # Save single point (real-time)
        >>> point = DataPoint(timestamp=datetime.now(), value=1234.5)
        >>> storage.save_datapoints_bulk("sessions_10min", [point])
        >>>
        >>> # Save multiple points (bulk load)
        >>> points = [
        ...     DataPoint(timestamp=datetime(2024, 11, 2, 14, 0), value=1200.0),
        ...     DataPoint(timestamp=datetime(2024, 11, 2, 14, 10), value=1250.0),
        ... ]
        >>> storage.save_datapoints_bulk("sessions_10min", points)
        >>>
        >>> # Get checkpoint (resume interrupted load)
        >>> last = storage.get_last_loaded_timestamp("sessions_10min")
        >>> if last:
        ...     print(f"Resume from {last}")
    """

    # Table creation SQL
    # Using ReplacingMergeTree to prevent duplicate data on re-loads
    DATAPOINTS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS dtk_datapoints (
        metric_name String,
        collected_at DateTime64(3),
        value Float64,
        is_missing UInt8,  -- Boolean flag for NULL values
        context String  -- JSON string for flexibility
    ) ENGINE = ReplacingMergeTree()
    PARTITION BY toYYYYMM(collected_at)
    ORDER BY (metric_name, collected_at)
    SETTINGS index_granularity = 8192;
    """

    DETECTIONS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS dtk_detections (
        id UInt64,
        metric_name String,
        detector_id String,  -- Unique detector identifier (for multi-detector support)
        detected_at DateTime64(3),
        value Float64,
        is_anomaly UInt8,  -- Boolean as UInt8
        anomaly_score Nullable(Float64),
        lower_bound Nullable(Float64),
        upper_bound Nullable(Float64),
        direction Nullable(String),
        percent_deviation Nullable(Float64),
        detector_type String,
        detector_params String,  -- JSON string with full params for transparency
        alert_sent UInt8,
        alert_reason Nullable(String),
        alerter_type Nullable(String),
        context String  -- JSON string
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(detected_at)
    ORDER BY (metric_name, detector_id, detected_at)
    SETTINGS index_granularity = 8192;
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize ClickHouse storage.

        Args:
            config: Storage configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config = config
        self.validate_config(config)

        # Extract connection parameters
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 9000)
        self.database = config.get("database", "default")
        self.user = config.get("user")
        self.password = config.get("password")
        self.timeout = config.get("timeout", 30)
        self.secure = config.get("secure", False)
        self.save_detections_enabled = config.get("save_detections", False)

        # Initialize client
        self.client: Client | None = None

        # Ensure tables exist
        self._ensure_tables_exist()

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate storage configuration.

        Args:
            config: Configuration to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # ClickHouse storage doesn't require mandatory parameters
        # (has sensible defaults)
        pass

    def _get_client(self) -> Client:
        """Get or create ClickHouse client.

        Returns:
            ClickHouse client instance

        Raises:
            StorageError: If connection fails
        """
        if self.client is None:
            try:
                self.client = Client(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    connect_timeout=self.timeout,
                    send_receive_timeout=self.timeout,
                    secure=self.secure,
                )
                logger.debug(f"Connected to ClickHouse storage: {self.host}:{self.port}/{self.database}")
            except Exception as e:
                raise StorageError(
                    f"Failed to connect to ClickHouse: {e}",
                    operation="connect",
                )
        return self.client

    def _ensure_tables_exist(self) -> None:
        """Ensure dtk_datapoints and dtk_detections tables exist."""
        try:
            client = self._get_client()

            # Create dtk_datapoints table
            client.execute(self.DATAPOINTS_TABLE_SQL)
            logger.debug("Ensured dtk_datapoints table exists")

            # Create dtk_detections table
            client.execute(self.DETECTIONS_TABLE_SQL)
            logger.debug("Ensured dtk_detections table exists")

        except Exception as e:
            raise StorageError(
                f"Failed to create storage tables: {e}",
                operation="create_tables",
            )

    def save_datapoints_bulk(
        self,
        metric_name: str,
        datapoints: list[DataPoint],
    ) -> None:
        """Bulk insert collected metric values to dtk_datapoints table.

        This method works for ANY number of datapoints:
        - Single point: [DataPoint(...)] - for real-time collection
        - Multiple points: [DataPoint(...), ...] - for bulk loading

        Uses ReplacingMergeTree to prevent duplicates on re-loads.
        If you load the same (metric_name, timestamp) twice, ClickHouse
        will automatically deduplicate during merges.

        Args:
            metric_name: Name of metric
            datapoints: List of data points to save (1 to 10,000+ points)

        Raises:
            StorageError: If save operation fails

        Example:
            >>> # Real-time (1 point)
            >>> storage.save_datapoints_bulk("sessions", [point])
            >>>
            >>> # Bulk load (4,464 points for 30 days at 10-min intervals)
            >>> storage.save_datapoints_bulk("sessions", points)
        """
        if not datapoints:
            logger.debug(f"No datapoints to save for {metric_name}")
            return

        try:
            client = self._get_client()

            # Prepare batch data
            batch_data = []
            for dp in datapoints:
                # Serialize metadata to JSON
                context_json = json.dumps(dp.metadata) if dp.metadata else "{}"

                # Handle NULL values (is_missing flag)
                value = dp.value if dp.value is not None else 0.0
                is_missing = 1 if dp.is_missing else 0

                batch_data.append(
                    (
                        metric_name,
                        dp.timestamp,
                        value,
                        is_missing,
                        context_json,
                    )
                )

            # Bulk insert
            client.execute(
                "INSERT INTO dtk_datapoints (metric_name, collected_at, value, is_missing, context) VALUES",
                batch_data,
            )

            logger.debug(
                f"Bulk saved {len(datapoints)} datapoints for {metric_name} "
                f"(period: {datapoints[0].timestamp} to {datapoints[-1].timestamp})"
            )

        except ClickHouseError as e:
            raise StorageError(
                f"Failed to bulk save datapoints to ClickHouse: {e}",
                operation="save_datapoints_bulk",
                details={
                    "metric_name": metric_name,
                    "count": len(datapoints),
                    "period_start": str(datapoints[0].timestamp) if datapoints else None,
                    "period_finish": str(datapoints[-1].timestamp) if datapoints else None,
                },
            )
        except Exception as e:
            raise StorageError(
                f"Unexpected error bulk saving datapoints: {e}",
                operation="save_datapoints_bulk",
            )

    def get_last_loaded_timestamp(self, metric_name: str) -> datetime | None:
        """Get timestamp of last loaded datapoint for checkpoint system.

        This method is used for:
        - Resuming interrupted bulk loads
        - Checking what data is already present
        - Avoiding duplicate inserts (though ReplacingMergeTree handles this)

        Args:
            metric_name: Name of metric to check

        Returns:
            Timestamp of most recent datapoint, or None if no data exists

        Raises:
            StorageError: If query fails

        Example:
            >>> last = storage.get_last_loaded_timestamp("sessions")
            >>> if last:
            >>>     print(f"Last data: {last}")
            >>>     resume_from = last + timedelta(minutes=10)
            >>> else:
            >>>     print("No data loaded yet, starting from scratch")
        """
        try:
            client = self._get_client()

            # Query most recent timestamp for this metric
            query = """
            SELECT MAX(collected_at) as last_timestamp
            FROM dtk_datapoints
            WHERE metric_name = %(metric_name)s
            """
            params = {"metric_name": metric_name}

            result = client.execute(query, params)

            # Extract timestamp from result
            if result and result[0] and result[0][0] is not None:
                last_timestamp = result[0][0]
                logger.debug(f"Last loaded timestamp for {metric_name}: {last_timestamp}")
                return last_timestamp
            else:
                logger.debug(f"No data loaded yet for {metric_name}")
                return None

        except ClickHouseError as e:
            raise StorageError(
                f"Failed to get last loaded timestamp from ClickHouse: {e}",
                operation="get_last_loaded_timestamp",
                details={"metric_name": metric_name},
            )
        except Exception as e:
            raise StorageError(
                f"Unexpected error getting last loaded timestamp: {e}",
                operation="get_last_loaded_timestamp",
            )

    def query_datapoints(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Query historical datapoints from dtk_datapoints table.

        Args:
            metric_name: Name of metric to query
            window: Size of historical window
                   String: "30 days", "7 days", "24 hours"
                   Int: Number of most recent data points
            end_time: End of time window (default: now())

        Returns:
            DataFrame with columns: timestamp, value, context
            Sorted by timestamp ascending

        Raises:
            StorageError: If query fails
            ValueError: If window format invalid
        """
        end_time = end_time or datetime.now()

        try:
            client = self._get_client()

            # Build query based on window type
            if isinstance(window, int):
                # Query last N points
                query = f"""
                SELECT
                    collected_at as timestamp,
                    value,
                    context
                FROM dtk_datapoints
                WHERE metric_name = %(metric_name)s
                  AND collected_at <= %(end_time)s
                ORDER BY collected_at DESC
                LIMIT {window}
                """
                params = {"metric_name": metric_name, "end_time": end_time}

            elif isinstance(window, str):
                # Parse time-based window (e.g., "30 days", "24 hours")
                start_time = self._parse_time_window(window, end_time)

                query = """
                SELECT
                    collected_at as timestamp,
                    value,
                    context
                FROM dtk_datapoints
                WHERE metric_name = %(metric_name)s
                  AND collected_at >= %(start_time)s
                  AND collected_at <= %(end_time)s
                ORDER BY collected_at ASC
                """
                params = {
                    "metric_name": metric_name,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            else:
                raise ValueError(f"Invalid window type: {type(window)}")

            # Execute query
            result = client.execute(query, params)

            # Convert to DataFrame
            df = pd.DataFrame(result, columns=["timestamp", "value", "context"])

            # If queried by count (DESC order), reverse to ASC
            if isinstance(window, int) and not df.empty:
                df = df.iloc[::-1].reset_index(drop=True)

            logger.debug(f"Queried {len(df)} datapoints for {metric_name}")
            return df

        except ClickHouseError as e:
            raise StorageError(
                f"Failed to query datapoints from ClickHouse: {e}",
                operation="query_datapoints",
            )
        except ValueError:
            raise
        except Exception as e:
            raise StorageError(
                f"Unexpected error querying datapoints: {e}",
                operation="query_datapoints",
            )

    def save_detection(
        self,
        metric_name: str,
        detection: DetectionResult,
        detector_id: str,
        alert_sent: bool = False,
        alert_reason: str | None = None,
        alerter_type: str | None = None,
    ) -> None:
        """Save detection result to dtk_detections table (if enabled).

        Args:
            metric_name: Name of metric
            detection: Detection result
            detector_id: Unique detector identifier (from DetectorConfig.id)
            alert_sent: Whether alert was sent
            alert_reason: Reason for alert
            alerter_type: Type of alerter used

        Raises:
            StorageError: If save operation fails
        """
        if not self.save_detections_enabled:
            return  # Detections saving disabled

        try:
            client = self._get_client()

            # Generate ID that includes detector_id for uniqueness
            # Format: timestamp_microseconds + hash(detector_id)
            timestamp_part = int(detection.timestamp.timestamp() * 1_000_000)
            detector_hash = abs(hash(detector_id)) % 1_000_000  # 6-digit hash
            row_id = timestamp_part * 1_000_000 + detector_hash

            # Serialize metadata to JSON
            detector_params_json = json.dumps(detection.metadata) if detection.metadata else "{}"
            context_json = "{}"

            # Insert data
            client.execute(
                """
                INSERT INTO dtk_detections (
                    id, metric_name, detector_id, detected_at, value, is_anomaly, anomaly_score,
                    lower_bound, upper_bound, direction, percent_deviation,
                    detector_type, detector_params, alert_sent, alert_reason, alerter_type, context
                ) VALUES
                """,
                [
                    (
                        row_id,
                        metric_name,
                        detector_id,
                        detection.timestamp,
                        detection.value,
                        1 if detection.is_anomaly else 0,
                        detection.score,
                        detection.lower_bound,
                        detection.upper_bound,
                        detection.direction,
                        detection.percent_deviation,
                        detection.metadata.get("detector_type", "unknown") if detection.metadata else "unknown",
                        detector_params_json,
                        1 if alert_sent else 0,
                        alert_reason,
                        alerter_type,
                        context_json,
                    )
                ],
            )

            logger.debug(f"Saved detection for {metric_name} (detector={detector_id}): anomaly={detection.is_anomaly}")

        except ClickHouseError as e:
            raise StorageError(
                f"Failed to save detection to ClickHouse: {e}",
                operation="save_detection",
            )
        except Exception as e:
            raise StorageError(
                f"Unexpected error saving detection: {e}",
                operation="save_detection",
            )

    def query_detections(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
        anomalies_only: bool = False,
    ) -> pd.DataFrame:
        """Query historical detections from dtk_detections table.

        Args:
            metric_name: Name of metric to query
            window: Size of historical window
            end_time: End of time window (default: now())
            anomalies_only: If True, only return anomalies

        Returns:
            DataFrame with detection results
            Sorted by timestamp ascending

        Raises:
            StorageError: If query fails
        """
        end_time = end_time or datetime.now()

        try:
            client = self._get_client()

            # Build base query
            anomaly_filter = "AND is_anomaly = 1" if anomalies_only else ""

            if isinstance(window, int):
                query = f"""
                SELECT *
                FROM dtk_detections
                WHERE metric_name = %(metric_name)s
                  AND detected_at <= %(end_time)s
                  {anomaly_filter}
                ORDER BY detected_at DESC
                LIMIT {window}
                """
                params = {"metric_name": metric_name, "end_time": end_time}

            elif isinstance(window, str):
                start_time = self._parse_time_window(window, end_time)
                query = f"""
                SELECT *
                FROM dtk_detections
                WHERE metric_name = %(metric_name)s
                  AND detected_at >= %(start_time)s
                  AND detected_at <= %(end_time)s
                  {anomaly_filter}
                ORDER BY detected_at ASC
                """
                params = {
                    "metric_name": metric_name,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            else:
                raise ValueError(f"Invalid window type: {type(window)}")

            result = client.execute(query, params)

            if not result:
                return pd.DataFrame()

            # Convert to DataFrame
            columns = [
                "id",
                "metric_name",
                "timestamp",
                "value",
                "is_anomaly",
                "anomaly_score",
                "lower_bound",
                "upper_bound",
                "direction",
                "percent_deviation",
                "detector_type",
                "detector_params",
                "alert_sent",
                "alert_reason",
                "alerter_type",
                "context",
            ]
            df = pd.DataFrame(result, columns=columns)

            # If queried by count, reverse order
            if isinstance(window, int) and not df.empty:
                df = df.iloc[::-1].reset_index(drop=True)

            logger.debug(f"Queried {len(df)} detections for {metric_name}")
            return df

        except ClickHouseError as e:
            raise StorageError(
                f"Failed to query detections from ClickHouse: {e}",
                operation="query_detections",
            )
        except ValueError:
            raise
        except Exception as e:
            raise StorageError(
                f"Unexpected error querying detections: {e}",
                operation="query_detections",
            )

    def cleanup_old_data(
        self,
        datapoints_retention_days: int,
        detections_retention_days: int | None = None,
    ) -> tuple[int, int]:
        """Delete old data based on retention policies.

        Args:
            datapoints_retention_days: Keep datapoints for N days
            detections_retention_days: Keep detections for N days (None = keep forever)

        Returns:
            Tuple of (datapoints_deleted, detections_deleted)

        Raises:
            StorageError: If cleanup fails
        """
        try:
            client = self._get_client()

            # Calculate cutoff dates
            datapoints_cutoff = datetime.now() - timedelta(days=datapoints_retention_days)

            # Cleanup datapoints
            result = client.execute(
                "DELETE FROM dtk_datapoints WHERE collected_at < %(cutoff)s",
                {"cutoff": datapoints_cutoff},
            )
            datapoints_deleted = result[0][0] if result and result[0] else 0

            # Cleanup detections (if retention specified)
            detections_deleted = 0
            if detections_retention_days is not None:
                detections_cutoff = datetime.now() - timedelta(days=detections_retention_days)
                result = client.execute(
                    "DELETE FROM dtk_detections WHERE detected_at < %(cutoff)s",
                    {"cutoff": detections_cutoff},
                )
                detections_deleted = result[0][0] if result and result[0] else 0

            logger.info(
                f"Cleaned up old data: {datapoints_deleted} datapoints, {detections_deleted} detections"
            )
            return datapoints_deleted, detections_deleted

        except ClickHouseError as e:
            raise StorageError(
                f"Failed to cleanup old data from ClickHouse: {e}",
                operation="cleanup_old_data",
            )
        except Exception as e:
            raise StorageError(
                f"Unexpected error during cleanup: {e}",
                operation="cleanup_old_data",
            )

    def _parse_time_window(self, window: str, end_time: datetime) -> datetime:
        """Parse time window string to start datetime.

        Args:
            window: Time window string (e.g., "30 days", "24 hours")
            end_time: End time

        Returns:
            Start datetime

        Raises:
            ValueError: If window format is invalid
        """
        window = window.lower().strip()
        parts = window.split()

        if len(parts) != 2:
            raise ValueError(f"Invalid window format: {window}. Expected format: 'N days/hours/minutes'")

        try:
            amount = int(parts[0])
            unit = parts[1]

            if unit in ("day", "days"):
                delta = timedelta(days=amount)
            elif unit in ("hour", "hours"):
                delta = timedelta(hours=amount)
            elif unit in ("minute", "minutes"):
                delta = timedelta(minutes=amount)
            elif unit in ("second", "seconds"):
                delta = timedelta(seconds=amount)
            else:
                raise ValueError(f"Unsupported time unit: {unit}")

            return end_time - delta

        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid window format: {window}. Error: {e}")

    def close(self) -> None:
        """Close ClickHouse connection and cleanup resources."""
        if self.client is not None:
            try:
                self.client.disconnect()
                logger.debug("Disconnected from ClickHouse storage")
            except Exception as e:
                logger.warning(f"Error disconnecting from ClickHouse storage: {e}")
            finally:
                self.client = None
