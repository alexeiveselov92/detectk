"""Generic SQL collector for DetectK using SQLAlchemy.

Supports PostgreSQL, MySQL, and SQLite databases.
"""

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from jinja2 import Template, TemplateError

from detectk.base import BaseCollector
from detectk.exceptions import CollectionError, ConfigurationError
from detectk.models import DataPoint
from detectk.registry import CollectorRegistry

logger = logging.getLogger(__name__)


@CollectorRegistry.register("sql")
class GenericSQLCollector(BaseCollector):
    """Generic SQL collector using SQLAlchemy.

    Supports PostgreSQL, MySQL, and SQLite databases through
    SQLAlchemy connection strings.

    The query MUST use Jinja2 variables and return multiple rows:
    - {{ period_start }} - Start of time period (required)
    - {{ period_finish }} - End of time period (required)
    - {{ interval }} - Time interval (e.g., "10 minutes")

    Query MUST return columns specified in config (timestamp_column, value_column).

    Configuration:
        connection_string: SQLAlchemy connection string (required)
                          Examples:
                          - postgresql://user:pass@localhost:5432/db
                          - mysql://user:pass@localhost:3306/db
                          - sqlite:///path/to/db.db
        query: SQL query using {{ period_start }}, {{ period_finish }}, {{ interval }}
        timeout: Query timeout in seconds (default: 30)
        pool_size: Connection pool size (default: 5)
        max_overflow: Max overflow connections (default: 10)
        timestamp_column: Name of timestamp column in results (from CollectorConfig)
        value_column: Name of value column in results (from CollectorConfig)
        context_columns: List of context column names (from CollectorConfig)

    Example:
        >>> from detectk_sql import GenericSQLCollector
        >>> config = {
        ...     "connection_string": "postgresql://localhost/analytics",
        ...     "query": '''
        ...         SELECT
        ...             DATE_TRUNC('minute', timestamp) AS period_time,
        ...             COUNT(*) AS value
        ...         FROM events
        ...         WHERE timestamp >= '{{ period_start }}'
        ...           AND timestamp < '{{ period_finish }}'
        ...         GROUP BY period_time
        ...         ORDER BY period_time
        ...     ''',
        ...     "timestamp_column": "period_time",
        ...     "value_column": "value",
        ... }
        >>> collector = GenericSQLCollector(config)
        >>> points = collector.collect_bulk(
        ...     period_start=datetime(2024, 11, 2, 14, 0),
        ...     period_finish=datetime(2024, 11, 2, 14, 10),
        ... )

    Supported Databases:
        - PostgreSQL (requires psycopg2-binary)
        - MySQL (requires mysqlclient)
        - SQLite (built-in)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Generic SQL collector.

        Args:
            config: Collector configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config = config
        self.validate_config(config)

        # Extract connection parameters
        self.connection_string = config["connection_string"]
        self.query_template = config["query"]  # Store as Jinja2 template
        self.timeout = config.get("timeout", 30)
        self.pool_size = config.get("pool_size", 5)
        self.max_overflow = config.get("max_overflow", 10)
        self.interval = config.get("interval", "10 minutes")  # Default interval

        # Column mapping
        self.timestamp_column = config.get("timestamp_column", "period_time")
        self.value_column = config.get("value_column", "value")
        self.context_columns = config.get("context_columns")

        # Initialize SQLAlchemy engine (lazy connection)
        self.engine: Engine | None = None

        # Detect database type from connection string
        self.db_type = self._detect_db_type(self.connection_string)

        logger.debug(f"Initialized {self.db_type} collector")

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate collector configuration.

        Args:
            config: Configuration to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if "connection_string" not in config:
            raise ConfigurationError(
                "SQL collector requires 'connection_string' parameter",
                config_path="collector.params",
            )

        if "query" not in config:
            raise ConfigurationError(
                "SQL collector requires 'query' parameter",
                config_path="collector.params",
            )

        query = config["query"].strip()
        if not query:
            raise ConfigurationError(
                "SQL collector query cannot be empty",
                config_path="collector.params.query",
            )

        # Check for required Jinja2 variables
        required_vars = ["period_start", "period_finish"]
        for var in required_vars:
            if f"{{{{ {var} }}}}" not in query and f"{{{{{var}}}}}" not in query:
                raise ConfigurationError(
                    f"SQL query must use Jinja2 variable {{{{ {var} }}}}\n"
                    f"Example: WHERE timestamp >= '{{{{ {var} }}}}'",
                    config_path="collector.params.query",
                )

        # Validate connection string format
        conn_str = config["connection_string"]
        if not any(conn_str.startswith(prefix) for prefix in ["postgresql://", "mysql://", "sqlite:///"]):
            raise ConfigurationError(
                "Invalid connection string format. Must start with postgresql://, mysql://, or sqlite:///",
                config_path="collector.params.connection_string",
            )

    def _detect_db_type(self, connection_string: str) -> str:
        """Detect database type from connection string.

        Args:
            connection_string: SQLAlchemy connection string

        Returns:
            Database type: 'postgresql', 'mysql', or 'sqlite'
        """
        if connection_string.startswith("postgresql://"):
            return "postgresql"
        elif connection_string.startswith("mysql://"):
            return "mysql"
        elif connection_string.startswith("sqlite:///"):
            return "sqlite"
        else:
            return "unknown"

    def _get_engine(self) -> Engine:
        """Get or create SQLAlchemy engine.

        Returns:
            SQLAlchemy engine instance

        Raises:
            CollectionError: If engine creation fails
        """
        if self.engine is None:
            try:
                # Create engine with connection pooling
                # For SQLite, disable pooling (not needed for file-based DB)
                if self.db_type == "sqlite":
                    self.engine = create_engine(
                        self.connection_string,
                        connect_args={"timeout": self.timeout},
                        poolclass=None,  # Disable pooling for SQLite
                    )
                else:
                    self.engine = create_engine(
                        self.connection_string,
                        pool_size=self.pool_size,
                        max_overflow=self.max_overflow,
                        pool_pre_ping=True,  # Verify connections before using
                        connect_args={"connect_timeout": self.timeout} if self.db_type == "postgresql" else {},
                    )

                logger.debug(f"Created {self.db_type} engine: {self.connection_string.split('@')[-1] if '@' in self.connection_string else self.connection_string}")
            except Exception as e:
                raise CollectionError(
                    f"Failed to create SQL engine: {e}",
                    source="sql",
                )

        return self.engine

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        """Collect time series data for a period from SQL database.

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

        Example Query (PostgreSQL):
            SELECT
                DATE_TRUNC('minute', timestamp) AS period_time,
                COUNT(*) AS value,
                EXTRACT(HOUR FROM period_time) AS hour_of_day
            FROM events
            WHERE timestamp >= '{{ period_start }}'
              AND timestamp < '{{ period_finish }}'
            GROUP BY period_time
            ORDER BY period_time

        Example Query (MySQL):
            SELECT
                DATE_FORMAT(timestamp, '%Y-%m-%d %H:%i:00') AS period_time,
                COUNT(*) AS value
            FROM events
            WHERE timestamp >= '{{ period_start }}'
              AND timestamp < '{{ period_finish }}'
            GROUP BY period_time
            ORDER BY period_time

        Example Query (SQLite):
            SELECT
                STRFTIME('%Y-%m-%d %H:%M:00', timestamp) AS period_time,
                COUNT(*) AS value
            FROM events
            WHERE timestamp >= '{{ period_start }}'
              AND timestamp < '{{ period_finish }}'
            GROUP BY period_time
            ORDER BY period_time
        """
        try:
            engine = self._get_engine()

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
                    source="sql",
                )

            # Execute rendered query
            logger.debug(
                f"Executing SQL query for period {period_start} to {period_finish}"
            )
            logger.debug(f"Rendered query: {rendered_query[:200]}...")

            with engine.connect() as conn:
                df = pd.read_sql_query(text(rendered_query), conn)

            # Handle empty result (no data in period)
            if df.empty:
                logger.info(
                    f"SQL query returned no rows for period "
                    f"{period_start} to {period_finish}. "
                    f"This is normal if no data exists in this time range."
                )
                return []

            # Validate required columns exist
            if self.timestamp_column not in df.columns:
                raise CollectionError(
                    f"Query result missing timestamp column: '{self.timestamp_column}'\n"
                    f"Available columns: {list(df.columns)}",
                    source="sql",
                )

            if self.value_column not in df.columns:
                raise CollectionError(
                    f"Query result missing value column: '{self.value_column}'\n"
                    f"Available columns: {list(df.columns)}",
                    source="sql",
                )

            # Parse result rows into DataPoints
            datapoints = []
            for idx, row in df.iterrows():
                try:
                    # Extract timestamp
                    timestamp_value = row[self.timestamp_column]
                    if pd.isna(timestamp_value):
                        logger.warning(f"Row {idx} has NULL timestamp, skipping")
                        continue

                    timestamp = pd.to_datetime(timestamp_value)

                    # Extract value
                    value_raw = row[self.value_column]
                    if pd.isna(value_raw):
                        # Allow NULL values (missing data)
                        value = None
                    else:
                        try:
                            value = float(value_raw)
                        except (TypeError, ValueError):
                            logger.warning(
                                f"Row {idx} has non-numeric value: {value_raw}, skipping"
                            )
                            continue

                    # Extract context (if configured)
                    context = None
                    if self.context_columns:
                        context = {}
                        for col in self.context_columns:
                            if col in df.columns:
                                context[col] = row[col]

                    # Create DataPoint
                    datapoint = DataPoint(
                        timestamp=timestamp,
                        value=value,
                        is_missing=(value is None),
                        metadata=context or {
                            "source": "sql",
                            "db_type": self.db_type,
                        },
                    )
                    datapoints.append(datapoint)

                except Exception as e:
                    logger.warning(f"Error parsing row {idx}: {e}, skipping row")
                    continue

            logger.debug(
                f"Collected {len(datapoints)} datapoints for period "
                f"{period_start} to {period_finish}"
            )

            return datapoints

        except SQLAlchemyError as e:
            raise CollectionError(
                f"SQL query failed: {e} (period: {period_start} to {period_finish})",
                source="sql",
            )
        except CollectionError:
            raise
        except Exception as e:
            raise CollectionError(
                f"Unexpected error during SQL collection: {e} (period: {period_start} to {period_finish})",
                source="sql",
            )

    def close(self) -> None:
        """Close database connection and cleanup resources.

        Disposes SQLAlchemy engine and connection pool.
        """
        if self.engine is not None:
            logger.debug(f"Closing {self.db_type} engine")
            self.engine.dispose()
            self.engine = None
