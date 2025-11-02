"""ClickHouse collector for DetectK."""

import logging
from datetime import datetime
from typing import Any

from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError
from jinja2 import Template, TemplateError

from detectk.base import BaseCollector
from detectk.models import DataPoint
from detectk.exceptions import CollectionError, ConfigurationError
from detectk.registry import CollectorRegistry

logger = logging.getLogger(__name__)


@CollectorRegistry.register("clickhouse")
class ClickHouseCollector(BaseCollector):
    """Collector for ClickHouse database.

    Executes SQL queries against ClickHouse and returns time series data.
    Supports connection pooling, query templating, and error handling.

    The query MUST use Jinja2 variables and return multiple rows:
    - {{ period_start }} - Start of time period (required)
    - {{ period_finish }} - End of time period (required)
    - {{ interval }} - Time interval (e.g., "10 minutes")

    Query MUST return columns specified in config (timestamp_column, value_column).

    Configuration:
        host: ClickHouse server host (default: localhost)
        port: ClickHouse server port (default: 9000)
        database: Database name (default: default)
        user: Username (optional)
        password: Password (optional)
        query: SQL query using {{ period_start }}, {{ period_finish }}, {{ interval }}
        timeout: Query timeout in seconds (default: 30)
        secure: Use SSL connection (default: False)
        timestamp_column: Name of timestamp column in results (from CollectorConfig)
        value_column: Name of value column in results (from CollectorConfig)
        context_columns: List of context column names (from CollectorConfig)

    Example:
        >>> from detectk_clickhouse import ClickHouseCollector
        >>> from detectk.registry import CollectorRegistry
        >>>
        >>> config = {
        ...     "host": "localhost",
        ...     "database": "analytics",
        ...     "query": '''
        ...         SELECT
        ...             toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        ...             count() AS value
        ...         FROM events
        ...         WHERE timestamp >= toDateTime('{{ period_start }}')
        ...           AND timestamp < toDateTime('{{ period_finish }}')
        ...         GROUP BY period_time
        ...         ORDER BY period_time
        ...     ''',
        ...     "timestamp_column": "period_time",
        ...     "value_column": "value",
        ... }
        >>> collector = ClickHouseCollector(config)
        >>> # Collect last 10 minutes
        >>> points = collector.collect_bulk(
        ...     period_start=datetime(2024, 11, 2, 14, 0),
        ...     period_finish=datetime(2024, 11, 2, 14, 10),
        ... )
        >>> print(f"Collected {len(points)} points")
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
        self.query_template = config["query"]  # Store as Jinja2 template
        self.timeout = config.get("timeout", 30)
        self.secure = config.get("secure", False)
        self.interval = config.get("interval", "10 minutes")  # Default interval

        # Column mapping
        self.timestamp_column = config.get("timestamp_column", "period_time")
        self.value_column = config.get("value_column", "value")
        self.context_columns = config.get("context_columns")

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

        # Check for required Jinja2 variables
        required_vars = ["period_start", "period_finish"]
        for var in required_vars:
            if f"{{{{ {var} }}}}" not in query and f"{{{{{var}}}}}" not in query:
                raise ConfigurationError(
                    f"ClickHouse query must use Jinja2 variable {{{{ {var} }}}}\n"
                    f"Example: WHERE timestamp >= toDateTime('{{{{ {var} }}}}')",
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

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        """Collect time series data for a period from ClickHouse.

        This method works for ANY time range:
        - Real-time: 10 minutes → 1 point
        - Bulk load: 30 days → 4,464 points (for 10-min intervals)

        The query is executed with period_start and period_finish variables.
        Query must return rows with columns: timestamp_column, value_column, context_columns.

        Args:
            period_start: Start of time period (inclusive)
            period_finish: End of time period (exclusive)

        Returns:
            List of DataPoints with timestamps, values, and optional context.
            Can be empty if no data in period.

        Raises:
            CollectionError: If query fails or returns invalid data

        Example Query:
            SELECT
                toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
                count() AS value,
                toHour(period_time) AS hour_of_day
            FROM events
            WHERE timestamp >= toDateTime('{{ period_start }}')
              AND timestamp < toDateTime('{{ period_finish }}')
            GROUP BY period_time
            ORDER BY period_time

        Note: Query template is stored in self.query_template with Jinja2 variables.
        This method renders it with period_start/period_finish for each call.
        """
        try:
            client = self._get_client()

            # Render query template with period_start, period_finish, interval
            try:
                template = Template(self.query_template)
                rendered_query = template.render(
                    period_start=period_start.isoformat(),
                    period_finish=period_finish.isoformat(),
                    interval=self.interval,
                )
            except TemplateError as e:
                raise CollectionError(
                    f"Failed to render query template: {e}\n"
                    f"Query template: {self.query_template[:200]}...",
                    source="clickhouse",
                )

            # Execute rendered query
            logger.debug(
                f"Executing ClickHouse query for period {period_start} to {period_finish}"
            )
            logger.debug(f"Rendered query: {rendered_query[:200]}...")
            result = client.execute(rendered_query)

            # Handle empty result (no data in period)
            if not result:
                logger.info(
                    f"ClickHouse query returned no rows for period "
                    f"{period_start} to {period_finish}. "
                    f"This is normal if no data exists in this time range."
                )
                return []

            # Parse result rows into DataPoints
            datapoints = []
            for row_num, row in enumerate(result):
                try:
                    # Extract timestamp
                    timestamp_value = row[0] if isinstance(row, (list, tuple)) else row.get(self.timestamp_column)
                    if not timestamp_value:
                        logger.warning(
                            f"Row {row_num} missing timestamp column '{self.timestamp_column}', skipping"
                        )
                        continue

                    if not isinstance(timestamp_value, datetime):
                        try:
                            timestamp = datetime.fromisoformat(str(timestamp_value))
                        except Exception:
                            logger.warning(
                                f"Row {row_num} has invalid timestamp format: {timestamp_value}, skipping"
                            )
                            continue
                    else:
                        timestamp = timestamp_value

                    # Extract value
                    value_raw = row[1] if isinstance(row, (list, tuple)) else row.get(self.value_column)
                    if value_raw is None:
                        # Allow NULL values (missing data)
                        value = None
                    else:
                        try:
                            value = float(value_raw)
                        except (TypeError, ValueError):
                            logger.warning(
                                f"Row {row_num} has non-numeric value: {value_raw}, skipping"
                            )
                            continue

                    # Extract context (if configured)
                    context = None
                    if self.context_columns and isinstance(row, dict):
                        context = {col: row.get(col) for col in self.context_columns if col in row}

                    # Create DataPoint
                    datapoint = DataPoint(
                        timestamp=timestamp,
                        value=value,
                        is_missing=(value is None),
                        metadata=context or {
                            "source": "clickhouse",
                            "host": self.host,
                            "database": self.database,
                        },
                    )
                    datapoints.append(datapoint)

                except Exception as e:
                    logger.warning(f"Error parsing row {row_num}: {e}, skipping row")
                    continue

            logger.debug(
                f"Collected {len(datapoints)} datapoints for period "
                f"{period_start} to {period_finish}"
            )

            return datapoints

        except ClickHouseError as e:
            raise CollectionError(
                f"ClickHouse query failed: {e}",
                source="clickhouse",
                details={
                    "period_start": str(period_start),
                    "period_finish": str(period_finish),
                },
            )
        except CollectionError:
            raise
        except Exception as e:
            raise CollectionError(
                f"Unexpected error during ClickHouse collection: {e}",
                source="clickhouse",
                details={
                    "period_start": str(period_start),
                    "period_finish": str(period_finish),
                },
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
