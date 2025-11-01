"""Threshold-based anomaly detector for DetectK.

Simple but powerful detector that compares metric values against static thresholds.
Supports multiple comparison operators and percentage-based thresholds.
"""

import logging
from datetime import datetime
from typing import Any, Literal

from detectk.base import BaseDetector, BaseStorage
from detectk.models import DetectionResult
from detectk.exceptions import DetectionError, ConfigurationError
from detectk.registry import DetectorRegistry

logger = logging.getLogger(__name__)


@DetectorRegistry.register("threshold")
class ThresholdDetector(BaseDetector):
    """Threshold-based anomaly detector.

    Detects anomalies by comparing metric values against static thresholds.
    Supports multiple operators and both absolute and percentage-based comparisons.

    Configuration:
        threshold: Threshold value (required)
        operator: Comparison operator (default: "greater_than")
                 Options: "greater_than", "less_than", "equals", "not_equals",
                         "between", "outside"
        upper_threshold: Upper bound for "between"/"outside" operators (optional)
        percent: If true, threshold is percentage change from baseline (optional)
        baseline: Baseline value for percentage calculation (required if percent=true)

    Operators:
        - greater_than: value > threshold
        - greater_equal: value >= threshold
        - less_than: value < threshold
        - less_equal: value <= threshold
        - equals: value == threshold (with tolerance)
        - not_equals: value != threshold (with tolerance)
        - between: threshold <= value <= upper_threshold
        - outside: value < threshold OR value > upper_threshold

    Example (absolute threshold):
        >>> detector = ThresholdDetector(
        ...     storage=None,
        ...     threshold=1000,
        ...     operator="greater_than"
        ... )
        >>> result = detector.detect("sessions", 1500, datetime.now())
        >>> print(result.is_anomaly)  # True (1500 > 1000)

    Example (percentage change):
        >>> detector = ThresholdDetector(
        ...     storage=None,
        ...     threshold=10.0,  # 10% increase
        ...     operator="greater_than",
        ...     percent=True,
        ...     baseline=1000
        ... )
        >>> result = detector.detect("sessions", 1150, datetime.now())
        >>> print(result.is_anomaly)  # True (15% > 10%)

    Example (range check):
        >>> detector = ThresholdDetector(
        ...     storage=None,
        ...     threshold=900,
        ...     upper_threshold=1100,
        ...     operator="outside"
        ... )
        >>> result = detector.detect("sessions", 1200, datetime.now())
        >>> print(result.is_anomaly)  # True (1200 outside [900, 1100])
    """

    VALID_OPERATORS = {
        "greater_than",
        "greater_equal",
        "less_than",
        "less_equal",
        "equals",
        "not_equals",
        "between",
        "outside",
    }

    def __init__(
        self,
        storage: BaseStorage | None,
        threshold: float,
        operator: Literal[
            "greater_than",
            "greater_equal",
            "less_than",
            "less_equal",
            "equals",
            "not_equals",
            "between",
            "outside",
        ] = "greater_than",
        upper_threshold: float | None = None,
        percent: bool = False,
        baseline: float | None = None,
        tolerance: float = 0.001,
        **kwargs: Any,
    ) -> None:
        """Initialize threshold detector.

        Args:
            storage: Storage backend (not used by this detector)
            threshold: Threshold value (or lower bound for range operators)
            operator: Comparison operator
            upper_threshold: Upper bound for "between"/"outside" operators
            percent: If true, threshold is percentage change
            baseline: Baseline value for percentage calculation
            tolerance: Tolerance for "equals"/"not_equals" (default: 0.001)
            **kwargs: Additional arguments (ignored)

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.storage = storage
        self.threshold = threshold
        self.operator = operator
        self.upper_threshold = upper_threshold
        self.percent = percent
        self.baseline = baseline
        self.tolerance = tolerance

        # Validate configuration
        self.validate_config({
            "threshold": threshold,
            "operator": operator,
            "upper_threshold": upper_threshold,
            "percent": percent,
            "baseline": baseline,
            "tolerance": tolerance,
        })

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate detector configuration (public interface from BaseDetector).

        Args:
            config: Configuration dictionary to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Extract params for internal validation
        threshold = config.get("threshold", self.threshold if hasattr(self, "threshold") else None)
        operator = config.get("operator", self.operator if hasattr(self, "operator") else "greater_than")
        upper_threshold = config.get("upper_threshold", self.upper_threshold if hasattr(self, "upper_threshold") else None)
        percent = config.get("percent", self.percent if hasattr(self, "percent") else False)
        baseline = config.get("baseline", self.baseline if hasattr(self, "baseline") else None)
        tolerance = config.get("tolerance", self.tolerance if hasattr(self, "tolerance") else 0.001)

        self._validate_config_internal(operator, threshold, upper_threshold, percent, baseline)

    def _validate_config_internal(
        self,
        operator: str,
        threshold: float,
        upper_threshold: float | None,
        percent: bool,
        baseline: float | None,
    ) -> None:
        """Validate detector configuration.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate operator
        if operator not in self.VALID_OPERATORS:
            raise ConfigurationError(
                f"Invalid operator '{operator}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_OPERATORS))}",
                config_path="detector.params.operator",
            )

        # Validate range operators
        if operator in ("between", "outside"):
            if upper_threshold is None:
                raise ConfigurationError(
                    f"Operator '{operator}' requires 'upper_threshold' parameter",
                    config_path="detector.params.upper_threshold",
                )
            if upper_threshold < threshold:
                raise ConfigurationError(
                    f"upper_threshold ({upper_threshold}) must be >= "
                    f"threshold ({threshold})",
                    config_path="detector.params",
                )

        # Validate percentage mode
        if percent:
            if baseline is None:
                raise ConfigurationError(
                    "Percentage mode requires 'baseline' parameter",
                    config_path="detector.params.baseline",
                )
            if baseline == 0:
                raise ConfigurationError(
                    "Baseline cannot be zero for percentage calculation",
                    config_path="detector.params.baseline",
                )

    def detect(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        **context: Any,
    ) -> DetectionResult:
        """Detect anomalies using threshold comparison.

        Args:
            metric_name: Name of metric
            value: Current metric value
            timestamp: Timestamp of measurement
            **context: Additional context (ignored)

        Returns:
            DetectionResult with anomaly status

        Raises:
            DetectionError: If detection fails
        """
        try:
            # Calculate comparison value (absolute or percentage)
            if self.percent:
                # Percentage change from baseline
                comparison_value = ((value - self.baseline) / abs(self.baseline)) * 100
                threshold_value = self.threshold
                upper_value = self.upper_threshold if self.upper_threshold else None
            else:
                # Absolute value
                comparison_value = value
                threshold_value = self.threshold
                upper_value = self.upper_threshold

            # Perform comparison based on operator
            is_anomaly = self._compare(comparison_value, threshold_value, upper_value)

            # Calculate anomaly score (distance from threshold)
            score = self._calculate_score(comparison_value, threshold_value, upper_value)

            # Determine direction
            direction = self._determine_direction(comparison_value, threshold_value, upper_value)

            # Calculate bounds for visualization
            lower_bound, upper_bound = self._calculate_bounds(threshold_value, upper_value)

            # Calculate percentage deviation
            if self.operator in ("between", "outside"):
                # For range operators, calculate deviation from nearest bound
                if comparison_value < threshold_value:
                    percent_dev = ((comparison_value - threshold_value) / abs(threshold_value)) * 100
                elif comparison_value > upper_value:
                    percent_dev = ((comparison_value - upper_value) / abs(upper_value)) * 100
                else:
                    percent_dev = 0.0
            else:
                # For simple operators, calculate deviation from threshold
                if threshold_value != 0:
                    percent_dev = ((comparison_value - threshold_value) / abs(threshold_value)) * 100
                else:
                    percent_dev = 0.0 if comparison_value == 0 else 100.0

            logger.debug(
                f"Threshold detection for {metric_name}: "
                f"value={value}, comparison={comparison_value:.2f}, "
                f"threshold={threshold_value}, operator={self.operator}, "
                f"is_anomaly={is_anomaly}"
            )

            return DetectionResult(
                metric_name=metric_name,
                timestamp=timestamp,
                value=value,
                is_anomaly=is_anomaly,
                score=score,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                direction=direction,
                percent_deviation=percent_dev if is_anomaly else None,
                metadata={
                    "detector_type": "threshold",
                    "threshold": self.threshold,
                    "operator": self.operator,
                    "upper_threshold": self.upper_threshold,
                    "percent_mode": self.percent,
                    "baseline": self.baseline,
                    "comparison_value": comparison_value,
                },
            )

        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            raise DetectionError(
                f"Threshold detection failed: {e}",
                detector_type="threshold",
            )

    def _compare(
        self,
        value: float,
        threshold: float,
        upper_threshold: float | None,
    ) -> bool:
        """Compare value against threshold(s) using configured operator.

        Args:
            value: Value to compare
            threshold: Threshold (or lower bound)
            upper_threshold: Upper bound (for range operators)

        Returns:
            True if anomaly detected
        """
        if self.operator == "greater_than":
            return value > threshold
        elif self.operator == "greater_equal":
            return value >= threshold
        elif self.operator == "less_than":
            return value < threshold
        elif self.operator == "less_equal":
            return value <= threshold
        elif self.operator == "equals":
            return abs(value - threshold) <= self.tolerance
        elif self.operator == "not_equals":
            return abs(value - threshold) > self.tolerance
        elif self.operator == "between":
            # Anomaly if value is INSIDE the range
            return threshold <= value <= upper_threshold
        elif self.operator == "outside":
            # Anomaly if value is OUTSIDE the range
            return value < threshold or value > upper_threshold
        else:
            # Should never reach here due to validation
            return False

    def _calculate_score(
        self,
        value: float,
        threshold: float,
        upper_threshold: float | None,
    ) -> float:
        """Calculate anomaly score (distance from threshold).

        Args:
            value: Value to score
            threshold: Threshold (or lower bound)
            upper_threshold: Upper bound (for range operators)

        Returns:
            Anomaly score (higher = more anomalous)
        """
        if self.operator in ("between", "outside"):
            # For range operators, score is distance from nearest boundary
            if value < threshold:
                return abs(value - threshold)
            elif upper_threshold and value > upper_threshold:
                return abs(value - upper_threshold)
            else:
                # Inside range
                return 0.0
        else:
            # For simple operators, score is distance from threshold
            return abs(value - threshold)

    def _determine_direction(
        self,
        value: float,
        threshold: float,
        upper_threshold: float | None,
    ) -> str | None:
        """Determine anomaly direction.

        Args:
            value: Current value
            threshold: Threshold (or lower bound)
            upper_threshold: Upper bound (for range operators)

        Returns:
            "up", "down", or None
        """
        if self.operator in ("greater_than", "greater_equal"):
            return "up" if value > threshold else None
        elif self.operator in ("less_than", "less_equal"):
            return "down" if value < threshold else None
        elif self.operator == "between":
            # Anomaly is being inside range - direction unclear
            return None
        elif self.operator == "outside":
            # Anomaly is being outside range
            if value < threshold:
                return "down"
            elif upper_threshold and value > upper_threshold:
                return "up"
            return None
        else:
            return None

    def _calculate_bounds(
        self,
        threshold: float,
        upper_threshold: float | None,
    ) -> tuple[float | None, float | None]:
        """Calculate expected bounds for visualization.

        Args:
            threshold: Threshold (or lower bound)
            upper_threshold: Upper bound (for range operators)

        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        if self.operator in ("greater_than", "greater_equal"):
            return (threshold, None)
        elif self.operator in ("less_than", "less_equal"):
            return (None, threshold)
        elif self.operator in ("between", "outside"):
            return (threshold, upper_threshold)
        elif self.operator == "equals":
            return (threshold - self.tolerance, threshold + self.tolerance)
        else:
            return (None, None)
