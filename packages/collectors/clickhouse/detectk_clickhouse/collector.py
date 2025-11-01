"""ClickHouse collector for DetectK."""

import logging
from datetime import datetime
from typing import Any

from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError

from detectk.base import BaseCollector
from detectk.models import DataPoint
from detectk.exceptions import CollectionError, ConfigurationError
from detectk.registry import CollectorRegistry

logger = logging.getLogger(__name__)


@CollectorRegistry.register("clickhouse")
class ClickHouseCollector(BaseCollector):
    """Collector for ClickHouse database.

    Executes SQL queries against ClickHouse and returns single data point.
    Supports connection pooling, query templating, and error handling.

    Configuration:
        host: ClickHouse server host (default: localhost)
        port: ClickHouse server port (default: 9000)
        database: Database name (default: default)
        user: Username (optional)
        password: Password (optional)
        query: SQL query that must return columns: value, timestamp
               Query can use Jinja2 templates (rendered by ConfigLoader)
        timeout: Query timeout in seconds (default: 30)
        secure: Use SSL connection (default: False)

    Example:
        >>> from detectk_clickhouse import ClickHouseCollector
        >>> from detectk.registry import CollectorRegistry
        >>>
        >>> config = {
        ...     "host": "localhost",
        ...     "database": "analytics",
        ...     "query": '''
        ...         SELECT
        ...             count() as value,
        ...             now() as timestamp
        ...         FROM events
        ...         WHERE timestamp > now() - INTERVAL 10 MINUTE
        ...     '''
        ... }
        >>> collector = ClickHouseCollector(config)
        >>> datapoint = collector.collect()
        >>> print(f"Value: {datapoint.value}")
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize ClickHouse collector.

        Args:
            config: Collector configuration

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
        self.query = config["query"]
        self.timeout = config.get("timeout", 30)
        self.secure = config.get("secure", False)

        # Initialize ClickHouse client
        self.client: Client | None = None

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate collector configuration.

        Args:
            config: Configuration to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if "query" not in config:
            raise ConfigurationError(
                "ClickHouse collector requires 'query' parameter",
                config_path="collector.params",
            )

        query = config["query"].strip()
        if not query:
            raise ConfigurationError(
                "ClickHouse collector query cannot be empty",
                config_path="collector.params.query",
            )

    def _get_client(self) -> Client:
        """Get or create ClickHouse client.

        Returns:
            ClickHouse client instance

        Raises:
            CollectionError: If connection fails
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
                logger.debug(f"Connected to ClickHouse: {self.host}:{self.port}/{self.database}")
            except Exception as e:
                raise CollectionError(
                    f"Failed to connect to ClickHouse: {e}",
                    source="clickhouse",
                )
        return self.client

    def collect(self, at_time: datetime | None = None) -> DataPoint:
        """Collect current metric value from ClickHouse.

        Executes the configured query and returns a single data point.
        Query must return columns: value (required), timestamp (optional).

        Args:
            at_time: Time to collect for (for backtesting support)
                    Note: at_time should be used in query template,
                    not passed to ClickHouse directly

        Returns:
            DataPoint with timestamp and value

        Raises:
            CollectionError: If query fails or returns invalid data

        Example Query:
            SELECT
                count() as value,
                now() as timestamp
            FROM events
            WHERE timestamp > now() - INTERVAL 10 MINUTE
        """
        at_time = at_time or datetime.now()

        try:
            client = self._get_client()

            # Execute query
            logger.debug(f"Executing ClickHouse query: {self.query[:100]}...")
            result = client.execute(self.query)

            # Validate result
            if not result:
                raise CollectionError(
                    "ClickHouse query returned no rows",
                    source="clickhouse",
                )

            row = result[0]
            if not row:
                raise CollectionError(
                    "ClickHouse query returned empty row",
                    source="clickhouse",
                )

            # Extract value and timestamp
            # Expected format: (value, timestamp) or just (value,)
            if len(row) < 1:
                raise CollectionError(
                    "ClickHouse query must return at least 'value' column",
                    source="clickhouse",
                )

            value = float(row[0])

            # Use returned timestamp if available, otherwise use at_time
            if len(row) >= 2 and row[1]:
                timestamp = row[1]
                if not isinstance(timestamp, datetime):
                    # Try to parse if it's a string
                    try:
                        timestamp = datetime.fromisoformat(str(timestamp))
                    except Exception:
                        timestamp = at_time
            else:
                timestamp = at_time

            logger.debug(f"Collected value: {value} at {timestamp}")

            return DataPoint(
                timestamp=timestamp,
                value=value,
                metadata={"source": "clickhouse", "host": self.host, "database": self.database},
            )

        except ClickHouseError as e:
            raise CollectionError(
                f"ClickHouse query failed: {e}",
                source="clickhouse",
            )
        except CollectionError:
            raise
        except Exception as e:
            raise CollectionError(
                f"Unexpected error during ClickHouse collection: {e}",
                source="clickhouse",
            )

    def close(self) -> None:
        """Close ClickHouse connection and cleanup resources."""
        if self.client is not None:
            try:
                self.client.disconnect()
                logger.debug("Disconnected from ClickHouse")
            except Exception as e:
                logger.warning(f"Error disconnecting from ClickHouse: {e}")
            finally:
                self.client = None
