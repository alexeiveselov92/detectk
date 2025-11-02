"""Data models for DetectK framework.

All models are implemented as dataclasses for immutability and type safety.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DataPoint:
    """Single metric measurement collected from data source.

    This represents a single point in time for a metric, with its value
    and optional metadata. Supports missing data detection.

    Attributes:
        timestamp: Time of measurement
        value: Metric value (float or None if missing)
               None indicates missing data (query returned no rows, partition missing, etc.)
        metadata: Optional additional context (e.g., raw value before casting,
                 seasonal features, custom tags, missing data indicators)
        is_missing: Whether data is missing (explicit flag)
                   True = query returned no data, partition missing, etc.
                   False = normal data point with value
        last_known_timestamp: Last time data was actually available (for staleness tracking)
                             Used to detect when data stream has stopped

    Missing Data Indicators:
        - value=None and is_missing=True: No data available
        - value=0.0 with metadata["is_empty_result"]=True: Backward compatibility (Phase 2)
        - last_known_timestamp: Track data freshness

    Example (Normal data):
        >>> point = DataPoint(
        ...     timestamp=datetime.now(),
        ...     value=1234.5,
        ...     metadata={"source": "clickhouse"}
        ... )

    Example (Missing data):
        >>> point = DataPoint(
        ...     timestamp=datetime.now(),
        ...     value=None,
        ...     is_missing=True,
        ...     last_known_timestamp=datetime(2024, 1, 1, 10, 0),
        ...     metadata={"reason": "partition_missing"}
        ... )
    """

    timestamp: datetime
    value: float | None  # None = missing data
    metadata: dict[str, Any] | None = None
    is_missing: bool = False  # Explicit missing data flag
    last_known_timestamp: datetime | None = None  # For staleness tracking


@dataclass(frozen=True)
class DetectionResult:
    """Result of anomaly detection for a single data point.

    Contains all information about the detection: whether the point is anomalous,
    confidence scores, expected bounds, and metadata for debugging.

    Attributes:
        metric_name: Name of the metric being monitored
        timestamp: Time of measurement
        value: Current metric value
        is_anomaly: Whether the point is considered anomalous
        score: Anomaly score (higher = more anomalous)
               For statistical detectors: z-score, MAD score, etc.
               For threshold detectors: distance from threshold
        lower_bound: Lower bound of expected range (None for one-sided detection)
        upper_bound: Upper bound of expected range (None for one-sided detection)
        direction: Direction of anomaly if detected
                  "up" - value above expected
                  "down" - value below expected
                  "missing" - data is missing
                  "stale" - data is too old
                  None - not anomalous or threshold-based
        percent_deviation: Percentage deviation from expected value
                          Calculated as: (value - expected) / abs(expected) * 100
        metadata: Additional context for debugging
                 May include: window_size, n_sigma, detector_params, etc.

    Example:
        >>> result = DetectionResult(
        ...     metric_name="sessions_10min",
        ...     timestamp=datetime.now(),
        ...     value=850.0,
        ...     is_anomaly=True,
        ...     score=4.2,
        ...     lower_bound=1000.0,
        ...     upper_bound=1500.0,
        ...     direction="down",
        ...     percent_deviation=-15.0,
        ...     metadata={"window_size": "30 days", "n_sigma": 3.0}
        ... )
    """

    metric_name: str
    timestamp: datetime
    value: float
    is_anomaly: bool
    score: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    direction: str | None = None  # "up", "down", or None
    percent_deviation: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AlertConditions:
    """Conditions that must be met before sending an alert.

    These conditions are checked by AlertAnalyzer before alerter sends a message.
    Allows fine-grained control over when alerts are actually sent.

    Attributes:
        consecutive_anomalies: Number of consecutive anomalies required
                              Default: 1 (alert on first anomaly)
        direction: Which direction of anomalies to alert on
                  "up" - only upward anomalies
                  "down" - only downward anomalies
                  "both" - either direction
                  "one" - any single direction in consecutive sequence
        min_deviation_percent: Minimum percentage deviation to trigger alert
                              Even if is_anomaly=True, won't alert if deviation
                              is below this threshold
        cooldown_minutes: Minimum minutes between alerts for same metric
                         Prevents spam when anomaly persists

    Example:
        >>> conditions = AlertConditions(
        ...     consecutive_anomalies=3,
        ...     direction="both",
        ...     min_deviation_percent=20.0,
        ...     cooldown_minutes=60
        ... )
    """

    consecutive_anomalies: int = 1
    direction: str = "both"  # "up", "down", "both", "one"
    min_deviation_percent: float | None = None
    cooldown_minutes: int = 0


@dataclass(frozen=True)
class CheckResult:
    """Result of complete metric check pipeline (collect → detect → alert).

    Contains all outputs from each stage of the pipeline for debugging and
    monitoring.

    Attributes:
        metric_name: Name of metric checked
        datapoint: Data collected from source
        detection: Detection result (anomaly status, bounds, etc.)
        alert_sent: Whether alert was actually sent
        alert_reason: Human-readable reason for alert decision
                     Examples:
                     - "3 consecutive upward anomalies detected"
                     - "Not alerted: only 2/3 consecutive anomalies"
                     - "Not alerted: within cooldown period"
        errors: List of errors encountered during pipeline
               Empty if pipeline completed successfully

    Example:
        >>> result = CheckResult(
        ...     metric_name="sessions_10min",
        ...     datapoint=DataPoint(...),
        ...     detection=DetectionResult(...),
        ...     alert_sent=True,
        ...     alert_reason="3 consecutive upward anomalies detected",
        ...     errors=[]
        ... )
    """

    metric_name: str
    datapoint: DataPoint
    detection: DetectionResult
    alert_sent: bool
    alert_reason: str | None = None
    errors: list[str] = field(default_factory=list)
