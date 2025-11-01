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
        "seasonal_features": [],
    },
    "zscore": {
        "n_sigma": 3.0,
        "seasonal_features": [],
    },
    # Add more detector defaults as detectors are implemented
}


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

    Supports both single detector and multiple detectors per metric.

    Attributes:
        name: Unique metric identifier
        description: Human-readable description
        collector: Data collection configuration
        detector: Single detector configuration (for backward compatibility)
        detectors: Multiple detector configurations (alternative to detector)
        alerter: Alert delivery configuration
        storage: Optional storage configuration
        backtest: Optional backtesting configuration
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
        # Validate backtest configuration
        if self.backtest.enabled:
            if not self.backtest.data_load_start:
                raise ValueError("backtest.data_load_start is required when backtesting is enabled")
            if not self.backtest.detection_start:
                raise ValueError("backtest.detection_start is required when backtesting is enabled")
            if not self.backtest.step_interval:
                raise ValueError("backtest.step_interval is required when backtesting is enabled")

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
