"""SQL storage for DetectK using SQLAlchemy.

Supports PostgreSQL, MySQL, and SQLite databases.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Boolean,
    Integer,
    Text,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, Session

from detectk.base import BaseStorage
from detectk.exceptions import ConfigurationError, StorageError
from detectk.models import DataPoint, DetectionResult
from detectk.registry import StorageRegistry

logger = logging.getLogger(__name__)

# SQLAlchemy base
Base = declarative_base()


class DtkDatapoint(Base):
    """SQLAlchemy model for dtk_datapoints table."""

    __tablename__ = "dtk_datapoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(255), nullable=False, index=True)
    collected_at = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)
    context = Column(Text)  # JSON string


class DtkDetection(Base):
    """SQLAlchemy model for dtk_detections table."""

    __tablename__ = "dtk_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(255), nullable=False, index=True)
    detector_id = Column(String(50), nullable=False, index=True)
    detected_at = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)
    is_anomaly = Column(Boolean, nullable=False)
    anomaly_score = Column(Float)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    direction = Column(String(10))
    percent_deviation = Column(Float)
    detector_type = Column(String(100), nullable=False)
    detector_params = Column(Text)  # JSON string
    alert_sent = Column(Boolean, default=False)
    alert_reason = Column(Text)
    alerter_type = Column(String(100))
    context = Column(Text)  # JSON string


@StorageRegistry.register("sql")
class SQLStorage(BaseStorage):
    """Generic SQL storage backend using SQLAlchemy.

    Manages two tables:
    1. dtk_datapoints - collected metric values
    2. dtk_detections - detection results (optional)

    Configuration:
        connection_string: SQLAlchemy connection string (required)
        save_detections: Save detection results (default: False)
        pool_size: Connection pool size (default: 5)
        max_overflow: Max overflow connections (default: 10)

    Example:
        >>> from detectk_sql import SQLStorage
        >>> config = {
        ...     "connection_string": "postgresql://localhost/detectk",
        ...     "save_detections": False,
        ... }
        >>> storage = SQLStorage(config)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize SQL storage.

        Args:
            config: Storage configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config = config
        self.validate_config(config)

        self.connection_string = config["connection_string"]
        self.save_detections_enabled = config.get("save_detections", False)
        self.pool_size = config.get("pool_size", 5)
        self.max_overflow = config.get("max_overflow", 10)

        # Detect database type
        self.db_type = self._detect_db_type(self.connection_string)

        # Initialize engine
        self.engine: Engine | None = None
        self._ensure_tables_exist()

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate storage configuration."""
        if "connection_string" not in config:
            raise ConfigurationError(
                "SQL storage requires 'connection_string' parameter",
                config_path="storage.params",
            )

    def _detect_db_type(self, connection_string: str) -> str:
        """Detect database type from connection string."""
        if connection_string.startswith("postgresql://"):
            return "postgresql"
        elif connection_string.startswith("mysql://"):
            return "mysql"
        elif connection_string.startswith("sqlite:///"):
            return "sqlite"
        else:
            return "unknown"

    def _get_engine(self) -> Engine:
        """Get or create SQLAlchemy engine."""
        if self.engine is None:
            try:
                if self.db_type == "sqlite":
                    self.engine = create_engine(
                        self.connection_string,
                        poolclass=None,
                    )
                else:
                    self.engine = create_engine(
                        self.connection_string,
                        pool_size=self.pool_size,
                        max_overflow=self.max_overflow,
                        pool_pre_ping=True,
                    )
                logger.debug(f"Created {self.db_type} storage engine")
            except Exception as e:
                raise StorageError(
                    f"Failed to create SQL engine: {e}",
                    storage_type="sql",
                )
        return self.engine

    def _ensure_tables_exist(self) -> None:
        """Create tables if they don't exist."""
        try:
            engine = self._get_engine()
            Base.metadata.create_all(engine)
            logger.debug(f"Ensured dtk_datapoints and dtk_detections tables exist")
        except Exception as e:
            raise StorageError(
                f"Failed to create tables: {e}",
                storage_type="sql",
            )

    def save_datapoint(self, metric_name: str, datapoint: DataPoint) -> None:
        """Save collected metric value."""
        try:
            engine = self._get_engine()

            # Prepare context JSON
            context_json = json.dumps(datapoint.metadata) if datapoint.metadata else None

            with Session(engine) as session:
                dp = DtkDatapoint(
                    metric_name=metric_name,
                    collected_at=datapoint.timestamp,
                    value=datapoint.value if datapoint.value is not None else 0.0,
                    context=context_json,
                )
                session.add(dp)
                session.commit()

            logger.debug(f"Saved datapoint for {metric_name}: value={datapoint.value}")

        except SQLAlchemyError as e:
            raise StorageError(
                f"Failed to save datapoint: {e}",
                storage_type="sql",
            )

    def save_detection(
        self,
        metric_name: str,
        detection: DetectionResult,
        alert_sent: bool = False,
        alert_reason: str | None = None,
        alerter_type: str | None = None,
    ) -> None:
        """Save detection result (if enabled)."""
        if not self.save_detections_enabled:
            return

        try:
            engine = self._get_engine()

            # Extract detector_id from metadata
            detector_id = detection.metadata.get("detector_id", "default") if detection.metadata else "default"
            detector_type = detection.metadata.get("detector_type", "unknown") if detection.metadata else "unknown"

            # Prepare JSON strings
            detector_params_json = json.dumps(detection.metadata) if detection.metadata else None
            context_json = None

            with Session(engine) as session:
                det = DtkDetection(
                    metric_name=metric_name,
                    detector_id=detector_id,
                    detected_at=detection.timestamp,
                    value=detection.value if detection.value is not None else 0.0,
                    is_anomaly=detection.is_anomaly,
                    anomaly_score=detection.score,
                    lower_bound=detection.lower_bound,
                    upper_bound=detection.upper_bound,
                    direction=detection.direction,
                    percent_deviation=detection.percent_deviation,
                    detector_type=detector_type,
                    detector_params=detector_params_json,
                    alert_sent=alert_sent,
                    alert_reason=alert_reason,
                    alerter_type=alerter_type,
                    context=context_json,
                )
                session.add(det)
                session.commit()

            logger.debug(f"Saved detection for {metric_name}: is_anomaly={detection.is_anomaly}")

        except SQLAlchemyError as e:
            raise StorageError(
                f"Failed to save detection: {e}",
                storage_type="sql",
            )

    def query_datapoints(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Query historical datapoints for a metric.

        Args:
            metric_name: Name of metric
            window: Time window ("30 days", "7 days", etc.) or number of points
            end_time: End of time window (default: now)

        Returns:
            DataFrame with columns: collected_at, value, context
        """
        end_time = end_time or datetime.now()

        try:
            engine = self._get_engine()

            # Parse window
            if isinstance(window, int):
                # Number of points
                query = text("""
                    SELECT collected_at, value, context
                    FROM dtk_datapoints
                    WHERE metric_name = :metric_name
                      AND collected_at <= :end_time
                    ORDER BY collected_at DESC
                    LIMIT :limit
                """)
                params = {"metric_name": metric_name, "end_time": end_time, "limit": window}
            else:
                # Time-based window (e.g., "30 days")
                parts = window.split()
                if len(parts) != 2:
                    raise ValueError(f"Invalid window format: {window}. Expected '<number> <unit>'")

                amount = int(parts[0])
                unit = parts[1].lower()

                if unit in ("day", "days"):
                    start_time = end_time - timedelta(days=amount)
                elif unit in ("hour", "hours"):
                    start_time = end_time - timedelta(hours=amount)
                elif unit in ("minute", "minutes"):
                    start_time = end_time - timedelta(minutes=amount)
                else:
                    raise ValueError(f"Unsupported time unit: {unit}")

                query = text("""
                    SELECT collected_at, value, context
                    FROM dtk_datapoints
                    WHERE metric_name = :metric_name
                      AND collected_at >= :start_time
                      AND collected_at <= :end_time
                    ORDER BY collected_at ASC
                """)
                params = {"metric_name": metric_name, "start_time": start_time, "end_time": end_time}

            with engine.connect() as conn:
                df = pd.read_sql_query(query, conn, params=params)

            logger.debug(f"Queried {len(df)} datapoints for {metric_name}")
            return df

        except SQLAlchemyError as e:
            raise StorageError(
                f"Failed to query datapoints: {e}",
                storage_type="sql",
            )
        except ValueError as e:
            raise StorageError(
                f"Invalid window format: {e}",
                storage_type="sql",
            )

    def query_detections(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Query historical detection results for cooldown logic."""
        if not self.save_detections_enabled:
            return pd.DataFrame()

        end_time = end_time or datetime.now()

        try:
            engine = self._get_engine()

            # Parse window (simplified - only time-based)
            parts = window.split() if isinstance(window, str) else [str(window), "minutes"]
            amount = int(parts[0])
            unit = parts[1].lower()

            if unit in ("day", "days"):
                start_time = end_time - timedelta(days=amount)
            elif unit in ("hour", "hours"):
                start_time = end_time - timedelta(hours=amount)
            elif unit in ("minute", "minutes"):
                start_time = end_time - timedelta(minutes=amount)
            else:
                raise ValueError(f"Unsupported time unit: {unit}")

            query = text("""
                SELECT detected_at, is_anomaly, alert_sent
                FROM dtk_detections
                WHERE metric_name = :metric_name
                  AND detected_at >= :start_time
                  AND detected_at <= :end_time
                ORDER BY detected_at DESC
            """)
            params = {"metric_name": metric_name, "start_time": start_time, "end_time": end_time}

            with engine.connect() as conn:
                df = pd.read_sql_query(query, conn, params=params)

            return df

        except SQLAlchemyError as e:
            raise StorageError(
                f"Failed to query detections: {e}",
                storage_type="sql",
            )

    def cleanup_old_data(
        self,
        datapoints_retention_days: int,
        detections_retention_days: int | None = None,
    ) -> tuple[int, int]:
        """Delete old data based on retention policies."""
        try:
            engine = self._get_engine()
            datapoints_cutoff = datetime.now() - timedelta(days=datapoints_retention_days)

            with engine.connect() as conn:
                # Delete old datapoints
                result_dp = conn.execute(
                    text("DELETE FROM dtk_datapoints WHERE collected_at < :cutoff"),
                    {"cutoff": datapoints_cutoff},
                )
                datapoints_deleted = result_dp.rowcount

                # Delete old detections if enabled
                detections_deleted = 0
                if self.save_detections_enabled and detections_retention_days:
                    detections_cutoff = datetime.now() - timedelta(days=detections_retention_days)
                    result_det = conn.execute(
                        text("DELETE FROM dtk_detections WHERE detected_at < :cutoff"),
                        {"cutoff": detections_cutoff},
                    )
                    detections_deleted = result_det.rowcount

                conn.commit()

            logger.info(
                f"Cleaned up old data: {datapoints_deleted} datapoints, {detections_deleted} detections"
            )
            return (datapoints_deleted, detections_deleted)

        except SQLAlchemyError as e:
            raise StorageError(
                f"Failed to cleanup old data: {e}",
                storage_type="sql",
            )

    def close(self) -> None:
        """Close database connection."""
        if self.engine is not None:
            logger.debug(f"Closing {self.db_type} storage engine")
            self.engine.dispose()
            self.engine = None
