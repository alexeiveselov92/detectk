"""Tests for ThresholdDetector."""

import pytest
from datetime import datetime

from detectk_detectors.threshold import ThresholdDetector
from detectk.exceptions import ConfigurationError
from detectk.registry import DetectorRegistry


def test_threshold_detector_registered() -> None:
    """Test that ThresholdDetector is registered."""
    assert DetectorRegistry.is_registered("threshold")
    detector_class = DetectorRegistry.get("threshold")
    assert detector_class is ThresholdDetector


def test_threshold_greater_than() -> None:
    """Test greater_than operator."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="greater_than")

    # Value > threshold → anomaly
    result = detector.detect("test_metric", 150, datetime.now())
    assert result.is_anomaly is True
    assert result.score == 50.0
    assert result.direction == "up"
    assert result.lower_bound == 100
    assert result.upper_bound is None

    # Value < threshold → no anomaly
    result = detector.detect("test_metric", 50, datetime.now())
    assert result.is_anomaly is False
    assert result.score == 50.0
    assert result.direction is None


def test_threshold_greater_equal() -> None:
    """Test greater_equal operator."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="greater_equal")

    # Value >= threshold → anomaly
    result = detector.detect("test_metric", 100, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 150, datetime.now())
    assert result.is_anomaly is True

    # Value < threshold → no anomaly
    result = detector.detect("test_metric", 99, datetime.now())
    assert result.is_anomaly is False


def test_threshold_less_than() -> None:
    """Test less_than operator."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="less_than")

    # Value < threshold → anomaly
    result = detector.detect("test_metric", 50, datetime.now())
    assert result.is_anomaly is True
    assert result.score == 50.0
    assert result.direction == "down"
    assert result.lower_bound is None
    assert result.upper_bound == 100

    # Value > threshold → no anomaly
    result = detector.detect("test_metric", 150, datetime.now())
    assert result.is_anomaly is False


def test_threshold_less_equal() -> None:
    """Test less_equal operator."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="less_equal")

    # Value <= threshold → anomaly
    result = detector.detect("test_metric", 100, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 50, datetime.now())
    assert result.is_anomaly is True

    # Value > threshold → no anomaly
    result = detector.detect("test_metric", 101, datetime.now())
    assert result.is_anomaly is False


def test_threshold_equals() -> None:
    """Test equals operator with tolerance."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="equals", tolerance=1.0)

    # Value within tolerance → anomaly
    result = detector.detect("test_metric", 100, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 100.5, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 99.5, datetime.now())
    assert result.is_anomaly is True

    # Value outside tolerance → no anomaly
    result = detector.detect("test_metric", 102, datetime.now())
    assert result.is_anomaly is False

    result = detector.detect("test_metric", 98, datetime.now())
    assert result.is_anomaly is False


def test_threshold_not_equals() -> None:
    """Test not_equals operator with tolerance."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="not_equals", tolerance=1.0)

    # Value outside tolerance → anomaly
    result = detector.detect("test_metric", 102, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 98, datetime.now())
    assert result.is_anomaly is True

    # Value within tolerance → no anomaly
    result = detector.detect("test_metric", 100, datetime.now())
    assert result.is_anomaly is False

    result = detector.detect("test_metric", 100.5, datetime.now())
    assert result.is_anomaly is False


def test_threshold_between() -> None:
    """Test between operator (inside range is anomaly)."""
    detector = ThresholdDetector(
        storage=None,
        threshold=90,
        upper_threshold=110,
        operator="between"
    )

    # Value inside range → anomaly
    result = detector.detect("test_metric", 100, datetime.now())
    assert result.is_anomaly is True
    assert result.lower_bound == 90
    assert result.upper_bound == 110

    result = detector.detect("test_metric", 90, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 110, datetime.now())
    assert result.is_anomaly is True

    # Value outside range → no anomaly
    result = detector.detect("test_metric", 89, datetime.now())
    assert result.is_anomaly is False

    result = detector.detect("test_metric", 111, datetime.now())
    assert result.is_anomaly is False


def test_threshold_outside() -> None:
    """Test outside operator (outside range is anomaly)."""
    detector = ThresholdDetector(
        storage=None,
        threshold=90,
        upper_threshold=110,
        operator="outside"
    )

    # Value outside range → anomaly
    result = detector.detect("test_metric", 89, datetime.now())
    assert result.is_anomaly is True
    assert result.direction == "down"
    assert result.score == 1.0

    result = detector.detect("test_metric", 111, datetime.now())
    assert result.is_anomaly is True
    assert result.direction == "up"
    assert result.score == 1.0

    # Value inside range → no anomaly
    result = detector.detect("test_metric", 100, datetime.now())
    assert result.is_anomaly is False
    assert result.score == 0.0

    result = detector.detect("test_metric", 90, datetime.now())
    assert result.is_anomaly is False

    result = detector.detect("test_metric", 110, datetime.now())
    assert result.is_anomaly is False


def test_threshold_percentage_mode() -> None:
    """Test percentage mode (threshold as percentage change from baseline)."""
    detector = ThresholdDetector(
        storage=None,
        threshold=10.0,  # 10% increase
        operator="greater_than",
        percent=True,
        baseline=1000
    )

    # 15% increase → anomaly
    result = detector.detect("test_metric", 1150, datetime.now())
    assert result.is_anomaly is True
    assert result.metadata["comparison_value"] == 15.0  # 15% change

    # 5% increase → no anomaly
    result = detector.detect("test_metric", 1050, datetime.now())
    assert result.is_anomaly is False
    assert result.metadata["comparison_value"] == 5.0

    # 10% decrease
    result = detector.detect("test_metric", 900, datetime.now())
    assert result.is_anomaly is False
    assert result.metadata["comparison_value"] == -10.0


def test_threshold_percentage_decrease() -> None:
    """Test percentage mode with decrease detection."""
    detector = ThresholdDetector(
        storage=None,
        threshold=-10.0,  # 10% decrease
        operator="less_than",
        percent=True,
        baseline=1000
    )

    # 15% decrease → anomaly
    result = detector.detect("test_metric", 850, datetime.now())
    assert result.is_anomaly is True
    assert result.metadata["comparison_value"] == -15.0

    # 5% decrease → no anomaly
    result = detector.detect("test_metric", 950, datetime.now())
    assert result.is_anomaly is False


def test_threshold_invalid_operator() -> None:
    """Test that invalid operator raises error."""
    with pytest.raises(ConfigurationError, match="Invalid operator"):
        ThresholdDetector(storage=None, threshold=100, operator="invalid")


def test_threshold_missing_upper_threshold() -> None:
    """Test that range operators require upper_threshold."""
    with pytest.raises(ConfigurationError, match="requires 'upper_threshold'"):
        ThresholdDetector(storage=None, threshold=90, operator="between")

    with pytest.raises(ConfigurationError, match="requires 'upper_threshold'"):
        ThresholdDetector(storage=None, threshold=90, operator="outside")


def test_threshold_invalid_range() -> None:
    """Test that upper_threshold must be >= threshold."""
    with pytest.raises(ConfigurationError, match="must be >= threshold"):
        ThresholdDetector(
            storage=None,
            threshold=110,
            upper_threshold=90,
            operator="between"
        )


def test_threshold_percentage_missing_baseline() -> None:
    """Test that percentage mode requires baseline."""
    with pytest.raises(ConfigurationError, match="requires 'baseline'"):
        ThresholdDetector(storage=None, threshold=10, operator="greater_than", percent=True)


def test_threshold_percentage_zero_baseline() -> None:
    """Test that baseline cannot be zero."""
    with pytest.raises(ConfigurationError, match="Baseline cannot be zero"):
        ThresholdDetector(
            storage=None,
            threshold=10,
            operator="greater_than",
            percent=True,
            baseline=0
        )


def test_threshold_metadata() -> None:
    """Test that detection result includes proper metadata."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="greater_than")

    result = detector.detect("test_metric", 150, datetime.now())

    assert result.metadata is not None
    assert result.metadata["detector_type"] == "threshold"
    assert result.metadata["threshold"] == 100
    assert result.metadata["operator"] == "greater_than"
    assert result.metadata["percent_mode"] is False
    assert result.metadata["comparison_value"] == 150


def test_threshold_percent_deviation() -> None:
    """Test percent_deviation calculation."""
    detector = ThresholdDetector(storage=None, threshold=100, operator="greater_than")

    # 50% above threshold
    result = detector.detect("test_metric", 150, datetime.now())
    assert result.is_anomaly is True
    assert result.percent_deviation == 50.0

    # No anomaly
    result = detector.detect("test_metric", 50, datetime.now())
    assert result.is_anomaly is False
    assert result.percent_deviation is None


def test_threshold_edge_cases() -> None:
    """Test edge cases."""
    detector = ThresholdDetector(storage=None, threshold=0, operator="greater_than")

    # Positive value with zero threshold
    result = detector.detect("test_metric", 1, datetime.now())
    assert result.is_anomaly is True

    # Negative value with zero threshold
    result = detector.detect("test_metric", -1, datetime.now())
    assert result.is_anomaly is False


def test_threshold_negative_values() -> None:
    """Test with negative thresholds and values."""
    detector = ThresholdDetector(storage=None, threshold=-100, operator="less_than")

    # -150 < -100 → anomaly
    result = detector.detect("test_metric", -150, datetime.now())
    assert result.is_anomaly is True
    assert result.direction == "down"

    # -50 > -100 → no anomaly
    result = detector.detect("test_metric", -50, datetime.now())
    assert result.is_anomaly is False


def test_threshold_zero_values() -> None:
    """Test with zero values."""
    detector = ThresholdDetector(storage=None, threshold=10, operator="greater_than")

    result = detector.detect("test_metric", 0, datetime.now())
    assert result.is_anomaly is False
    assert result.value == 0.0


def test_threshold_large_values() -> None:
    """Test with very large values."""
    detector = ThresholdDetector(storage=None, threshold=1e6, operator="greater_than")

    result = detector.detect("test_metric", 1e9, datetime.now())
    assert result.is_anomaly is True
    assert result.score == 999_000_000.0


def test_threshold_very_small_tolerance() -> None:
    """Test equals operator with very small tolerance."""
    detector = ThresholdDetector(
        storage=None,
        threshold=100.0,
        operator="equals",
        tolerance=0.0001
    )

    result = detector.detect("test_metric", 100.00005, datetime.now())
    assert result.is_anomaly is True

    result = detector.detect("test_metric", 100.001, datetime.now())
    assert result.is_anomaly is False
