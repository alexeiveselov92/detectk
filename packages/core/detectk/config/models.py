"""Configuration models using Pydantic for validation.

These models define the schema for metric configuration YAML files.
"""

from typing import Any
from pydantic import BaseModel, Field, field_validator


class CollectorConfig(BaseModel):
    """Configuration for data collector.

    Attributes:
        type: Collector type (e.g., "clickhouse", "postgres", "http")
        params: Collector-specific parameters (connection, query, etc.)

    Example:
        ```yaml
        collector:
          type: "clickhouse"
          params:
            host: "${CLICKHOUSE_HOST}"
            database: "analytics"
            query: "SELECT count() as value FROM events"
        ```
    """

    type: str = Field(..., description="Collector type (must be registered)")
    params: dict[str, Any] = Field(default_factory=dict, description="Collector-specific parameters")

    @field_validator("type")
    @classmethod
    def validate_type_not_empty(cls, v: str) -> str:
        """Ensure type is not empty."""
        if not v or not v.strip():
            raise ValueError("Collector type cannot be empty")
        return v.strip()


class StorageConfig(BaseModel):
    """Configuration for metrics history storage.

    Attributes:
        enabled: Whether to save metrics to storage
        type: Storage type (e.g., "clickhouse", "postgres")
        params: Storage-specific parameters
        retention_days: How long to keep historical data

    Example:
        ```yaml
        storage:
          enabled: true
          type: "clickhouse"
          params:
            connection_string: "${METRICS_DB_CONNECTION}"
          retention_days: 90
        ```
    """

    enabled: bool = Field(default=True, description="Enable storage of metrics history")
    type: str | None = Field(default=None, description="Storage type (must be registered)")
    params: dict[str, Any] = Field(default_factory=dict, description="Storage-specific parameters")
    retention_days: int = Field(default=90, description="Retention period in days", ge=1)


class DetectorConfig(BaseModel):
    """Configuration for anomaly detector.

    Attributes:
        type: Detector type (e.g., "threshold", "mad", "zscore")
        params: Detector-specific parameters

    Example:
        ```yaml
        detector:
          type: "mad"
          params:
            window_size: "30 days"
            n_sigma: 3.0
            seasonal_features:
              - name: "hour_of_day"
                expression: "toHour(timestamp)"
        ```
    """

    type: str = Field(..., description="Detector type (must be registered)")
    params: dict[str, Any] = Field(default_factory=dict, description="Detector-specific parameters")

    @field_validator("type")
    @classmethod
    def validate_type_not_empty(cls, v: str) -> str:
        """Ensure type is not empty."""
        if not v or not v.strip():
            raise ValueError("Detector type cannot be empty")
        return v.strip()


class AlerterConfig(BaseModel):
    """Configuration for alerter.

    Attributes:
        type: Alerter type (e.g., "mattermost", "slack", "telegram")
        params: Alerter-specific parameters (webhook, channel, etc.)
        conditions: Alert decision conditions

    Example:
        ```yaml
        alerter:
          type: "mattermost"
          params:
            webhook_url: "${MATTERMOST_WEBHOOK}"
            channel: "#ops-alerts"
          conditions:
            consecutive_anomalies: 3
            direction: "both"
            cooldown_minutes: 60
        ```
    """

    type: str = Field(..., description="Alerter type (must be registered)")
    params: dict[str, Any] = Field(default_factory=dict, description="Alerter-specific parameters")
    conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Alert conditions (consecutive_anomalies, direction, etc.)"
    )

    @field_validator("type")
    @classmethod
    def validate_type_not_empty(cls, v: str) -> str:
        """Ensure type is not empty."""
        if not v or not v.strip():
            raise ValueError("Alerter type cannot be empty")
        return v.strip()


class BacktestConfig(BaseModel):
    """Configuration for backtesting.

    Attributes:
        enabled: Whether backtesting is enabled
        data_load_start: Start time for loading historical data
        detection_start: Start time for running detection (after window)
        detection_end: End time for detection
        step_interval: Time step between checks

    Example:
        ```yaml
        backtest:
          enabled: true
          data_load_start: "2024-01-01"
          detection_start: "2024-02-01"
          detection_end: "2024-03-01"
          step_interval: "10 minutes"
        ```
    """

    enabled: bool = Field(default=False, description="Enable backtesting mode")
    data_load_start: str | None = Field(default=None, description="Start time for data loading")
    detection_start: str | None = Field(default=None, description="Start time for detection")
    detection_end: str | None = Field(default=None, description="End time for detection")
    step_interval: str | None = Field(default=None, description="Time step between checks")

    @field_validator("data_load_start", "detection_start", "detection_end")
    @classmethod
    def validate_dates_if_enabled(cls, v: str | None, info) -> str | None:
        """Validate required fields when backtesting is enabled."""
        # Note: Full validation happens in ConfigLoader after all fields are parsed
        return v


class MetricConfig(BaseModel):
    """Complete metric monitoring configuration.

    This is the top-level configuration model that combines all components
    needed for monitoring a single metric.

    Attributes:
        name: Unique metric identifier
        description: Human-readable description
        collector: Data collection configuration
        detector: Anomaly detection configuration
        alerter: Alert delivery configuration
        storage: Optional storage configuration
        backtest: Optional backtesting configuration
        metadata: Additional arbitrary metadata

    Example:
        ```yaml
        name: "sessions_10min"
        description: "Monitor user sessions every 10 minutes"

        collector:
          type: "clickhouse"
          params:
            host: "localhost"
            query: "SELECT count() as value FROM sessions"

        detector:
          type: "mad"
          params:
            window_size: "30 days"

        alerter:
          type: "mattermost"
          params:
            webhook_url: "https://mattermost.example.com/hooks/xxx"
        ```
    """

    name: str = Field(..., description="Unique metric identifier")
    description: str | None = Field(default=None, description="Human-readable description")

    collector: CollectorConfig = Field(..., description="Data collection configuration")
    detector: DetectorConfig = Field(..., description="Anomaly detection configuration")
    alerter: AlerterConfig = Field(..., description="Alert delivery configuration")

    storage: StorageConfig = Field(
        default_factory=StorageConfig,
        description="Metrics history storage configuration"
    )
    backtest: BacktestConfig = Field(
        default_factory=BacktestConfig,
        description="Backtesting configuration"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional arbitrary metadata"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure metric name is valid."""
        if not v or not v.strip():
            raise ValueError("Metric name cannot be empty")

        # Check for valid characters (alphanumeric, underscore, dash)
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                f"Metric name '{v}' contains invalid characters. "
                "Use only alphanumeric, underscore, and dash."
            )

        return v.strip()

    def model_post_init(self, __context: Any) -> None:
        """Additional validation after model initialization."""
        # Validate backtest configuration
        if self.backtest.enabled:
            if not self.backtest.data_load_start:
                raise ValueError("backtest.data_load_start is required when backtesting is enabled")
            if not self.backtest.detection_start:
                raise ValueError("backtest.detection_start is required when backtesting is enabled")
            if not self.backtest.step_interval:
                raise ValueError("backtest.step_interval is required when backtesting is enabled")
