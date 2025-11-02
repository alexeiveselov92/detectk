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

    Configuration:
        connection_string: SQLAlchemy connection string (required)
                          Examples:
                          - postgresql://user:pass@localhost:5432/db
                          - mysql://user:pass@localhost:3306/db
                          - sqlite:///path/to/db.db
        query: SQL query that returns 'value' column (required)
               Optional 'timestamp' column
        timeout: Query timeout in seconds (default: 30)
        pool_size: Connection pool size (default: 5)
        max_overflow: Max overflow connections (default: 10)

    Example:
        >>> from detectk_sql import GenericSQLCollector
        >>> config = {
        ...     "connection_string": "postgresql://localhost/analytics",
        ...     "query": '''
        ...         SELECT
        ...             COUNT(DISTINCT user_id) as value,
        ...             NOW() as timestamp
        ...         FROM sessions
        ...         WHERE created_at >= NOW() - INTERVAL '10 minutes'
        ...     '''
        ... }
        >>> collector = GenericSQLCollector(config)
        >>> datapoint = collector.collect()
        >>> print(f"Value: {datapoint.value}")

    Query Requirements:
        - Must return 'value' column (numeric)
        - Optional 'timestamp' column (datetime)
        - If timestamp not provided, uses current time

    Supported Databases:
        - PostgreSQL (requires psycopg2-binary)
        - MySQL (requires mysqlclient)
        - SQLite (built-in)

    Note on Empty Results:
        If query returns no rows, returns DataPoint with value=None
        and is_missing=True flag for explicit missing data detection.
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
        self.query = config["query"]
        self.timeout = config.get("timeout", 30)
        self.pool_size = config.get("pool_size", 5)
        self.max_overflow = config.get("max_overflow", 10)

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

    def collect(self, at_time: datetime | None = None) -> DataPoint:
        """Collect current metric value from SQL database.

        Executes the configured query and returns a single data point.
        Query must return 'value' column (required), 'timestamp' optional.

        Args:
            at_time: Time to collect for (for backtesting support)
                    Note: at_time should be used in query template,
                    not passed to SQL directly

        Returns:
            DataPoint with timestamp and value

        Raises:
            CollectionError: If query fails or returns invalid data

        Example Query (PostgreSQL):
            SELECT
                COUNT(*) as value,
                NOW() as timestamp
            FROM events
            WHERE created_at >= NOW() - INTERVAL '10 minutes'

        Example Query (MySQL):
            SELECT
                COUNT(*) as value,
                NOW() as timestamp
            FROM events
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)

        Example Query (SQLite):
            SELECT
                COUNT(*) as value,
                datetime('now') as timestamp
            FROM events
            WHERE timestamp >= datetime('now', '-10 minutes')

        Note on Empty Results:
            If query returns no rows, returns DataPoint with value=None
            and is_missing=True flag.
        """
        at_time = at_time or datetime.now()

        try:
            engine = self._get_engine()

            # Execute query using pandas for convenience
            logger.debug(f"Executing SQL query: {self.query[:100]}...")

            with engine.connect() as conn:
                df = pd.read_sql_query(text(self.query), conn)

            # Handle empty result (no rows returned)
            if df.empty:
                logger.warning(
                    "SQL query returned no rows. "
                    "Returning DataPoint with is_missing=True. "
                    "Consider using aggregate functions that always return a row."
                )
                return DataPoint(
                    timestamp=at_time,
                    value=None,
                    is_missing=True,
                    metadata={
                        "source": "sql",
                        "db_type": self.db_type,
                        "reason": "empty_result",
                        "warning": "Query returned no rows",
                    },
                )

            # Extract value column
            if "value" not in df.columns:
                raise CollectionError(
                    "SQL query must return 'value' column",
                    source="sql",
                )

            value = float(df.iloc[0]["value"])

            # Extract timestamp if provided
            if "timestamp" in df.columns:
                timestamp = pd.to_datetime(df.iloc[0]["timestamp"])
            else:
                timestamp = at_time

            logger.debug(f"Collected value: {value} at {timestamp}")

            return DataPoint(
                timestamp=timestamp,
                value=value,
                is_missing=False,
                metadata={
                    "source": "sql",
                    "db_type": self.db_type,
                },
            )

        except SQLAlchemyError as e:
            raise CollectionError(
                f"SQL query failed: {e}",
                source="sql",
            )
        except KeyError as e:
            raise CollectionError(
                f"Missing required column in query result: {e}",
                source="sql",
            )
        except (ValueError, TypeError) as e:
            raise CollectionError(
                f"Invalid value returned by query: {e}",
                source="sql",
            )
        except Exception as e:
            raise CollectionError(
                f"Unexpected error during collection: {e}",
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
