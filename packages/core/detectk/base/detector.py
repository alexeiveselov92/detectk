"""Base class for anomaly detectors.

All detectors must inherit from BaseDetector and implement the detect() method.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from detectk.models import DetectionResult
from detectk.base.storage import BaseStorage
from detectk.exceptions import DetectionError


class BaseDetector(ABC):
    """Abstract base class for all anomaly detectors.

    Detectors analyze metric data and determine if current values are anomalous.
    They read historical data from storage, apply detection algorithms, and return
    results with anomaly status, confidence scores, and expected bounds.

    Detectors are pure data science - they don't make alert decisions (that's
    AlertAnalyzer's job). They just answer: "Is this value anomalous?"

    Design principles:
    - Storage is injected via constructor (dependency injection)
    - Detector reads history from storage, doesn't store anything
    - Works with any time interval (no hardcoded assumptions)
    - Seasonal features computed dynamically from config
    - Returns rich DetectionResult with all context

    Example Implementation:
        >>> from detectk.base import BaseDetector
        >>> from detectk.registry import DetectorRegistry
        >>>
        >>> @DetectorRegistry.register("mad")
        >>> class MADDetector(BaseDetector):
        ...     def __init__(self, storage: BaseStorage, **params) -> None:
        ...         super().__init__(storage, **params)
        ...         self.window_size = params.get("window_size", "30 days")
        ...         self.n_sigma = params.get("n_sigma", 3.0)
        ...
        ...     def detect(self, metric_name: str, value: float,
        ...                timestamp: datetime, **context) -> DetectionResult:
        ...         # Read historical window from storage
        ...         history = self.storage.query(metric_name, self.window_size, timestamp)
        ...         # Apply MAD algorithm
        ...         # Return DetectionResult
        ...         pass
    """

    def __init__(self, storage: BaseStorage, **params: Any) -> None:
        """Initialize detector with storage and parameters.

        Args:
            storage: Storage instance for reading historical data
            **params: Detector-specific parameters from config
                     Common params: window_size, threshold, seasonal_features

        Example:
            >>> storage = ClickHouseStorage(config)
            >>> detector = MADDetector(
            ...     storage=storage,
            ...     window_size="30 days",
            ...     n_sigma=3.0,
            ...     use_weighted=True,
            ...     seasonal_features=[
            ...         {"name": "hour_of_day", "expression": "toHour(timestamp)"}
            ...     ]
            ... )
        """
        self.storage = storage
        self.params = params

    @abstractmethod
    def detect(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        **context: Any,
    ) -> DetectionResult:
        """Detect if current value is anomalous.

        This method should:
        1. Read historical window from storage
        2. Apply detection algorithm (threshold, statistical, ML, etc.)
        3. Calculate expected bounds
        4. Determine anomaly status and score
        5. Return DetectionResult with all metadata

        Args:
            metric_name: Name of metric (for reading history from storage)
            value: Current metric value to check
            timestamp: Timestamp of current value
            **context: Additional context from config
                      May include: seasonal_features, custom metadata, etc.

        Returns:
            DetectionResult with:
            - is_anomaly: Whether point is anomalous
            - score: Anomaly score (higher = more anomalous)
            - bounds: Expected lower/upper bounds
            - direction: "up", "down", or None
            - metadata: Detector-specific context for debugging

        Raises:
            DetectionError: If detection fails due to:
                - Insufficient historical data
                - Storage query failed
                - Calculation error (division by zero, etc.)
                - Invalid parameters

        Example:
            >>> detector = MADDetector(storage, window_size="30 days", n_sigma=3.0)
            >>> result = detector.detect(
            ...     metric_name="sessions_10min",
            ...     value=850.0,
            ...     timestamp=datetime.now(),
            ... )
            >>> if result.is_anomaly:
            ...     print(f"Anomaly! Score: {result.score:.2f}")
            ...     print(f"Expected: [{result.lower_bound:.0f}, {result.upper_bound:.0f}]")
        """
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate detector-specific configuration.

        Should check:
        - Required parameters present
        - Parameter values valid (e.g., n_sigma > 0)
        - Window size format valid
        - Seasonal features schema correct

        Args:
            config: Configuration dictionary to validate

        Raises:
            ConfigurationError: If config is invalid
        """
        pass

    def _parse_window_size(self, window: str | int, timestamp: datetime) -> tuple[datetime, datetime]:
        """Parse window size parameter into time range.

        Helper method for detector implementations.

        Args:
            window: Window size ("30 days" or number of points)
            timestamp: End time for window

        Returns:
            (start_time, end_time) tuple

        Raises:
            ValueError: If window format invalid

        Example:
            >>> start, end = detector._parse_window_size("30 days", datetime.now())
            >>> print(end - start)
            30 days, 0:00:00
        """
        from dateutil.relativedelta import relativedelta
        import re

        end_time = timestamp

        if isinstance(window, int):
            # Number of points - can't determine time range without data
            # Implementation should query last N points from storage
            raise ValueError("Point-based windows should be handled by query() method")

        if isinstance(window, str):
            # Parse time-based window: "30 days", "7 days", "24 hours"
            match = re.match(r"(\d+)\s*(day|days|hour|hours|minute|minutes)", window.lower())
            if not match:
                raise ValueError(f"Invalid window format: {window}. Expected '30 days', '24 hours', etc.")

            amount = int(match.group(1))
            unit = match.group(2).rstrip("s")  # Remove trailing 's'

            if unit == "day":
                start_time = end_time - relativedelta(days=amount)
            elif unit == "hour":
                start_time = end_time - relativedelta(hours=amount)
            elif unit == "minute":
                start_time = end_time - relativedelta(minutes=amount)
            else:
                raise ValueError(f"Unsupported time unit: {unit}")

            return start_time, end_time

        raise ValueError(f"Window must be string or int, got {type(window)}")
