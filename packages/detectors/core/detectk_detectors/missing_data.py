"""Missing Data Detector for DetectK.

Detects when data is missing, stale, or has gaps in the stream.
"""

import logging
from datetime import datetime, timedelta

from detectk.base import BaseDetector, BaseStorage
from detectk.exceptions import DetectionError
from detectk.models import DataPoint, DetectionResult
from detectk.registry import DetectorRegistry

logger = logging.getLogger(__name__)


@DetectorRegistry.register("missing_data")
class MissingDataDetector(BaseDetector):
    """Detector for missing or stale data.

    Alerts when:
    - Data is explicitly missing (is_missing=True)
    - Data is stale (last_known_timestamp too old)
    - Consecutive missing data points exceed threshold

    Unlike statistical detectors, this doesn't require historical window analysis.
    It directly checks if data is present and fresh.

    Parameters:
        consecutive_missing (int): Alert after N consecutive missing points (default: 1)
        max_staleness_minutes (int): Alert if data older than N minutes (default: None, disabled)
        treat_zero_as_missing (bool): Treat value=0 as missing (default: False)

    Example:
        ```yaml
        detector:
          type: "missing_data"
          params:
            consecutive_missing: 2
            max_staleness_minutes: 15
        ```

    Use Cases:
        - Heartbeat monitoring (is data stream alive?)
        - Partition availability checks
        - Data freshness monitoring
        - ETL job completion detection
    """

    def __init__(
        self,
        storage: BaseStorage,
        consecutive_missing: int = 1,
        max_staleness_minutes: int | None = None,
        treat_zero_as_missing: bool = False,
        **kwargs,
    ):
        """Initialize MissingDataDetector.

        Args:
            storage: Storage interface (not used, but required by BaseDetector)
            consecutive_missing: Number of consecutive missing points to trigger alert
            max_staleness_minutes: Maximum age of data in minutes (None = disabled)
            treat_zero_as_missing: Whether to treat value=0 as missing data
            **kwargs: Additional parameters (ignored)
        """
        super().__init__(storage, **kwargs)
        self.consecutive_missing = consecutive_missing
        self.max_staleness_minutes = max_staleness_minutes
        self.treat_zero_as_missing = treat_zero_as_missing

        # Track consecutive missing counts per metric
        self._missing_counts: dict[str, int] = {}

        logger.info(
            f"MissingDataDetector initialized: "
            f"consecutive_missing={consecutive_missing}, "
            f"max_staleness_minutes={max_staleness_minutes}"
        )

    def validate_config(self, config: dict) -> None:
        """Validate detector configuration.

        Args:
            config: Configuration dictionary

        Raises:
            ValueError: If configuration is invalid
        """
        consecutive_missing = config.get("consecutive_missing", 1)
        if consecutive_missing < 1:
            raise ValueError("consecutive_missing must be >= 1")

        max_staleness = config.get("max_staleness_minutes")
        if max_staleness is not None and max_staleness <= 0:
            raise ValueError("max_staleness_minutes must be > 0 if specified")

    def detect(
        self,
        metric_name: str,
        value: float | None,
        timestamp: datetime,
        **context,
    ) -> DetectionResult:
        """Detect if data is missing or stale.

        Args:
            metric_name: Name of metric
            value: Current value (None if missing)
            timestamp: Timestamp of measurement
            **context: Additional context (may include is_missing, last_known_timestamp)

        Returns:
            DetectionResult with direction="missing" or "stale" if anomalous
        """
        try:
            is_missing = context.get("is_missing", False)
            last_known_timestamp = context.get("last_known_timestamp")

            # Check 1: Explicit missing data flag
            if is_missing or value is None:
                return self._handle_missing(metric_name, timestamp)

            # Check 2: Treat zero as missing (optional)
            if self.treat_zero_as_missing and value == 0.0:
                return self._handle_missing(metric_name, timestamp)

            # Check 3: Staleness check
            if self.max_staleness_minutes and last_known_timestamp:
                staleness_minutes = (timestamp - last_known_timestamp).total_seconds() / 60
                if staleness_minutes > self.max_staleness_minutes:
                    return DetectionResult(
                        metric_name=metric_name,
                        timestamp=timestamp,
                        value=value,
                        is_anomaly=True,
                        score=staleness_minutes / self.max_staleness_minutes,  # How stale
                        direction="stale",
                        metadata={
                            "detector": "missing_data",
                            "staleness_minutes": staleness_minutes,
                            "max_staleness_minutes": self.max_staleness_minutes,
                            "last_known_timestamp": last_known_timestamp.isoformat(),
                        },
                    )

            # Data is present and fresh - reset missing count
            self._missing_counts[metric_name] = 0

            return DetectionResult(
                metric_name=metric_name,
                timestamp=timestamp,
                value=value,
                is_anomaly=False,
                score=0.0,
                metadata={"detector": "missing_data"},
            )

        except Exception as e:
            raise DetectionError(
                f"MissingDataDetector failed for {metric_name}: {e}",
                metric=metric_name,
            )

    def _handle_missing(self, metric_name: str, timestamp: datetime) -> DetectionResult:
        """Handle missing data point.

        Increments missing count and alerts if threshold exceeded.

        Args:
            metric_name: Name of metric
            timestamp: Timestamp of missing point

        Returns:
            DetectionResult with direction="missing" if threshold exceeded
        """
        # Increment missing count
        current_count = self._missing_counts.get(metric_name, 0) + 1
        self._missing_counts[metric_name] = current_count

        # Check if threshold exceeded
        is_anomaly = current_count >= self.consecutive_missing

        logger.warning(
            f"Missing data for {metric_name}: "
            f"{current_count}/{self.consecutive_missing} consecutive missing"
        )

        return DetectionResult(
            metric_name=metric_name,
            timestamp=timestamp,
            value=None,  # Missing value
            is_anomaly=is_anomaly,
            score=current_count / self.consecutive_missing,  # How many consecutive
            direction="missing",
            metadata={
                "detector": "missing_data",
                "consecutive_missing": current_count,
                "threshold": self.consecutive_missing,
                "alerted": is_anomaly,
            },
        )

    def reset_missing_count(self, metric_name: str) -> None:
        """Reset missing count for a metric.

        Useful for testing or manual reset after incident resolution.

        Args:
            metric_name: Name of metric to reset
        """
        self._missing_counts[metric_name] = 0
        logger.debug(f"Reset missing count for {metric_name}")
