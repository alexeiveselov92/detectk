"""Configuration models using Pydantic for validation.

These models define the schema for metric configuration YAML files.
"""

import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator


# Global registry of detector default parameters
# Used for parameter normalization when generating detector IDs
DETECTOR_DEFAULTS: dict[str, dict[str, Any]] = {
    "threshold": {
        "operator": "greater_than",
        "percent": False,
        "tolerance": 0.001,
    },
    "mad": {
        "n_sigma": 3.0,
        "use_weighted": True,
        "exp_decay_factor": 0.1,
        "seasonal_features": [],
        "use_combined_seasonality": False,
    },
    "zscore": {
        "n_sigma": 3.0,
        "use_weighted": True,
        "exp_decay_factor": 0.1,
        "seasonal_features": [],
        "use_combined_seasonality": False,
    },
    # Add more detector defaults as detectors are implemented
}


class CollectorConfig(BaseModel):
    """Configuration for data collector.

    Supports three ways to configure collector:
    1. Profile reference (recommended for reusable connections)
    2. Minimal config with env var defaults
    3. Full explicit configuration

    Attributes:
        type: Collector type (e.g., "clickhouse", "postgres", "http")
              Optional if profile is specified
        profile: Reference to connection profile (optional)
        params: Collector-specific parameters (connection, query, etc.)
        timestamp_column: Name of timestamp column in query results (default: "period_time")
        value_column: Name of value column in query results (default: "value")
        context_columns: Optional list of context column names (seasonal features, metadata)

    Query Requirements:
        The query must use Jinja2 variables and return multiple rows:
        - {{ period_start }} - Start of time period (required)
        - {{ period_finish }} - End of time period (required)
        - {{ interval }} - Time interval (e.g., "10 minutes")

        Required columns in result:
        - timestamp_column (e.g., "period_time") - Timestamp for each data point
        - value_column (e.g., "value") - Metric value for each data point
        - context_columns (optional) - Seasonal features like hour_of_day, day_of_week

    Example 1 - Using profile (recommended):
        ```yaml
        collector:
          profile: "clickhouse_analytics"
          params:
            query: |
              SELECT
                toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
                count() AS value,
                toHour(period_time) AS hour_of_day
              FROM events
              WHERE timestamp >= toDateTime('{{ period_start }}')
                AND timestamp < toDateTime('{{ period_finish }}')
              GROUP BY period_time
              ORDER BY period_time
          timestamp_column: "period_time"
          value_column: "value"
          context_columns: ["hour_of_day"]
        ```

    Example 2 - Minimal (defaults):
        ```yaml
        collector:
          type: "clickhouse"
          params:
            query: |
              SELECT
                period_time,
                sessions_count as value
              FROM ...
          # timestamp_column defaults to "period_time"
          # value_column defaults to "value"
        ```
    """

    type: str | None = Field(default=None, description="Collector type (must be registered)")
    profile: str | None = Field(default=None, description="Profile name from detectk_profiles.yaml")
    params: dict[str, Any] = Field(default_factory=dict, description="Collector-specific parameters")

    # Column mapping for query results
    timestamp_column: str = Field(
        default="period_time",
        description="Name of timestamp column in query results"
    )
    value_column: str = Field(
        default="value",
        description="Name of value column in query results"
    )
    context_columns: list[str] | None = Field(
        default=None,
        description="Optional list of context column names (seasonal features, metadata)"
    )

    @model_validator(mode="after")
    def validate_type_or_profile(self) -> "CollectorConfig":
        """Ensure either type or profile is specified."""
        if not self.type and not self.profile:
            raise ValueError("Either 'type' or 'profile' must be specified in collector config")
        return self

    @field_validator("type")
    @classmethod
    def validate_type_not_empty(cls, v: str | None) -> str | None:
        """Ensure type is not empty if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Collector type cannot be empty")
        return v.strip() if v else None


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

    Supports auto-generated deterministic IDs based on type and parameters.
    This allows multiple detectors per metric for A/B testing or parameter tuning.

    Attributes:
        id: Unique detector identifier (auto-generated if not provided)
        type: Detector type (e.g., "threshold", "mad", "zscore")
        params: Detector-specific parameters

    ID Generation:
        - If `id` is provided manually, it will be used as-is
        - If `id` is None, it will be auto-generated as 8-char hash from type + normalized params
        - Normalized params = params with default values removed for determinism
        - Canonical JSON serialization (sort_keys=True) ensures parameter order doesn't affect ID

    Example (single detector):
        ```yaml
        detector:
          type: "mad"
          params:
            window_size: "30 days"
            n_sigma: 3.0
        # id will be auto-generated: e.g., "a1b2c3d4"
        ```

    Example (multiple detectors with manual IDs):
        ```yaml
        detectors:
          - id: "mad_sigma3"
            type: "mad"
            params:
              window_size: "30 days"
              n_sigma: 3.0
          - id: "mad_sigma5"
            type: "mad"
            params:
              window_size: "30 days"
              n_sigma: 5.0
        ```

    Example (multiple detectors with auto IDs):
        ```yaml
        detectors:
          - type: "mad"
            params:
              window_size: "30 days"
              n_sigma: 3.0
            # id auto-generated: "a1b2c3d4"
          - type: "mad"
            params:
              window_size: "30 days"
              n_sigma: 5.0
            # id auto-generated: "b2c3d4e5" (different from above because n_sigma differs)
        ```
    """

    id: str | None = Field(
        default=None,
        description="Unique detector identifier (auto-generated if not provided)"
    )
    type: str = Field(..., description="Detector type (must be registered)")
    params: dict[str, Any] = Field(default_factory=dict, description="Detector-specific parameters")

    @field_validator("type")
    @classmethod
    def validate_type_not_empty(cls, v: str) -> str:
        """Ensure type is not empty."""
        if not v or not v.strip():
            raise ValueError("Detector type cannot be empty")
        return v.strip()

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str | None) -> str | None:
        """Validate manual ID format if provided."""
        if v is None:
            return None

        v = v.strip()
        if not v:
            raise ValueError("Detector ID cannot be empty string")

        # Allow alphanumeric, underscore, dash
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                f"Detector ID '{v}' contains invalid characters. "
                "Use only alphanumeric, underscore, and dash."
            )

        return v

    def _normalize_params(self) -> dict[str, Any]:
        """Remove default parameter values for deterministic ID generation.

        This ensures that params with defaults explicitly set generate the same
        ID as params without those keys.

        Example:
            {"n_sigma": 3.0, "window_size": "30 days"}
            normalized to:
            {"window_size": "30 days"}  # n_sigma=3.0 is default for MAD

        Returns:
            Normalized params dict with defaults removed
        """
        defaults = DETECTOR_DEFAULTS.get(self.type, {})
        normalized = {}

        for key, value in self.params.items():
            # Only include param if it differs from default
            if key not in defaults or defaults[key] != value:
                normalized[key] = value

        return normalized

    def _generate_id(self) -> str:
        """Generate deterministic 8-char hash from type + normalized params.

        Uses canonical JSON serialization (sort_keys=True) to ensure
        parameter order doesn't affect the hash.

        Returns:
            8-character hex string (first 8 chars of SHA256 hash)

        Example:
            type="mad", params={"window_size": "30 days", "n_sigma": 5.0}
            -> normalized: {"window_size": "30 days", "n_sigma": 5.0}
            -> canonical JSON: '{"n_sigma": 5.0, "window_size": "30 days"}'
            -> content: "mad:{"n_sigma": 5.0, "window_size": "30 days"}"
            -> SHA256 hash: "a1b2c3d4e5f6..."
            -> result: "a1b2c3d4"
        """
        normalized = self._normalize_params()
        canonical_json = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        content = f"{self.type}:{canonical_json}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()
        return hash_digest[:8]

    @model_validator(mode="after")
    def ensure_id_exists(self) -> "DetectorConfig":
        """Ensure ID is set (auto-generate if not provided)."""
        if self.id is None:
            self.id = self._generate_id()
        return self


class AlerterConfig(BaseModel):
    """Configuration for alerter.

    Attributes:
        enabled: Whether to send alerts (default: True)
                Set to False for historical data loading without alerts
        type: Alerter type (e.g., "mattermost", "slack", "telegram")
        params: Alerter-specific parameters (webhook, channel, etc.)
        conditions: Alert decision conditions

    Production Example:
        ```yaml
        alerter:
          enabled: true  # Send alerts (default)
          type: "mattermost"
          params:
            webhook_url: "${MATTERMOST_WEBHOOK}"
          conditions:
            consecutive_anomalies: 3
            cooldown_minutes: 60
        ```

    Historical Load Example (no alerts):
        ```yaml
        alerter:
          enabled: false  # Don't send alerts during historical load
          type: "mattermost"
          params:
            webhook_url: "${MATTERMOST_WEBHOOK}"
        ```
    """

    enabled: bool = Field(
        default=True,
        description="Whether to send alerts (False = detection only, no alerts)"
    )
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


class ScheduleConfig(BaseModel):
    """Configuration for scheduled metric checks.

    For both production and historical data loading (what was called "backtesting").

    Attributes:
        start_time: When to start checking (for historical: past date, for prod: now)
        end_time: When to stop (optional, for continuous monitoring leave None)
        interval: How often to check (e.g., "10 minutes")
        batch_load_days: For initial load, how many days to load per batch (default: 30)

    Production Example (continuous monitoring):
        ```yaml
        schedule:
          interval: "10 minutes"
          # No start_time/end_time - runs continuously from now
        ```

    Historical Load Example (one-time backfill):
        ```yaml
        schedule:
          start_time: "2024-01-01 00:00:00"  # Load from here
          end_time: "2024-11-01 00:00:00"    # Load until here
          interval: "10 minutes"
          batch_load_days: 30                # Load in 30-day batches

        alerter:
          enabled: false  # Don't send alerts during historical load
        ```

    Process (same for both production and historical):
        1. Check what's already in dtk_datapoints (checkpoint)
        2. For each interval from start to end:
           a. Collect: collector.collect_bulk(current - interval, current)
           b. Save: storage.save_datapoints_bulk(points)
           c. Detect: detector.detect(value, timestamp)
           d. Alert: if alerter.enabled and is_anomaly → send alert
    """

    start_time: str | None = Field(
        default=None,
        description="Start time for checking (None = start from now)"
    )
    end_time: str | None = Field(
        default=None,
        description="End time for checking (None = run continuously)"
    )
    interval: str = Field(
        default="10 minutes",
        description="How often to check (e.g., '10 minutes', '1 hour')"
    )
    batch_load_days: int = Field(
        default=30,
        description="For initial loads, how many days to load per batch"
    )


class MetricConfig(BaseModel):
    """Complete metric monitoring configuration.

    This is the top-level configuration model that combines all components
    needed for monitoring a single metric.

    Supports both single detector and multiple detectors per metric.

    Attributes:
        name: Unique metric identifier
        description: Human-readable description
        collector: Data collection configuration
        detector: Single detector configuration (for backward compatibility)
        detectors: Multiple detector configurations (alternative to detector)
        alerter: Alert delivery configuration
        storage: Optional storage configuration
        schedule: Optional schedule configuration (for both production and historical loads)
        metadata: Additional arbitrary metadata

    Example (single detector - backward compatible):
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

    Example (multiple detectors):
        ```yaml
        name: "sessions_10min"
        description: "Monitor user sessions with multiple detection strategies"

        collector:
          type: "clickhouse"
          params:
            host: "localhost"
            query: "SELECT count() as value FROM sessions"

        detectors:
          - type: "mad"
            params:
              window_size: "30 days"
              n_sigma: 3.0
          - type: "mad"
            params:
              window_size: "30 days"
              n_sigma: 5.0

        alerter:
          type: "mattermost"
          params:
            webhook_url: "https://mattermost.example.com/hooks/xxx"
        ```
    """

    name: str = Field(..., description="Unique metric identifier")
    description: str | None = Field(default=None, description="Human-readable description")

    collector: CollectorConfig = Field(..., description="Data collection configuration")

    # Support both single detector and multiple detectors
    detector: DetectorConfig | None = Field(
        default=None,
        description="Single detector configuration (for backward compatibility)"
    )
    detectors: list[DetectorConfig] | None = Field(
        default=None,
        description="Multiple detector configurations (alternative to detector)"
    )

    alerter: AlerterConfig = Field(..., description="Alert delivery configuration")

    storage: StorageConfig = Field(
        default_factory=StorageConfig,
        description="Metrics history storage configuration"
    )
    schedule: ScheduleConfig | None = Field(
        default=None,
        description="Schedule configuration (for both production and historical loads)"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional arbitrary metadata"
    )

    tags: list[str] = Field(
        default_factory=list,
        description="Tags for grouping and filtering metrics (e.g., ['critical', 'revenue', 'hourly'])"
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

    @model_validator(mode="after")
    def validate_detector_config(self) -> "MetricConfig":
        """Validate that exactly one of detector or detectors is provided."""
        if self.detector is None and self.detectors is None:
            raise ValueError("Either 'detector' or 'detectors' must be provided")

        if self.detector is not None and self.detectors is not None:
            raise ValueError("Cannot specify both 'detector' and 'detectors'. Use one or the other.")

        # If single detector provided, also populate detectors list for uniform handling
        # BUT keep detector field populated for backward compatibility
        if self.detector is not None and self.detectors is None:
            self.detectors = [self.detector]

        # If detectors list provided but detector is None (multiple detectors case)
        # Leave detector as None since it's ambiguous which one to use

        # Validate detectors list
        if self.detectors is not None:
            if len(self.detectors) == 0:
                raise ValueError("'detectors' list cannot be empty")

            # Check for duplicate detector IDs
            detector_ids = [d.id for d in self.detectors]
            if len(detector_ids) != len(set(detector_ids)):
                duplicates = [id_ for id_ in detector_ids if detector_ids.count(id_) > 1]
                raise ValueError(
                    f"Duplicate detector IDs found: {set(duplicates)}. "
                    "Each detector must have a unique ID within a metric."
                )

        return self

    def model_post_init(self, __context: Any) -> None:
        """Additional validation after model initialization."""
        # No additional validation needed for now
        # Schedule validation is handled by ScheduleConfig model itself
        pass

    def get_detectors(self) -> list[DetectorConfig]:
        """Get list of detectors for this metric.

        Returns:
            List of DetectorConfig objects (always a list, even for single detector)
        """
        if self.detectors is not None:
            return self.detectors
        elif self.detector is not None:
            return [self.detector]
        else:
            raise ValueError("No detectors configured")
