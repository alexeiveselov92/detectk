"""Tests for data models."""

from datetime import datetime
import pytest

from detectk.models import (
    DataPoint,
    DetectionResult,
    AlertConditions,
    CheckResult,
)


def test_datapoint_creation() -> None:
    """Test DataPoint creation with required fields."""
    now = datetime.now()
    point = DataPoint(timestamp=now, value=123.45)

    assert point.timestamp == now
    assert point.value == 123.45
    assert point.metadata is None


def test_datapoint_with_metadata() -> None:
    """Test DataPoint with optional metadata."""
    now = datetime.now()
    point = DataPoint(
        timestamp=now,
        value=123.45,
        metadata={"source": "clickhouse", "raw_value": 123},
    )

    assert point.metadata == {"source": "clickhouse", "raw_value": 123}


def test_datapoint_immutable() -> None:
    """Test that DataPoint is immutable (frozen)."""
    point = DataPoint(timestamp=datetime.now(), value=123.45)

    with pytest.raises(AttributeError):
        point.value = 999.0  # type: ignore


def test_detection_result_creation() -> None:
    """Test DetectionResult with all fields."""
    now = datetime.now()
    result = DetectionResult(
        metric_name="sessions_10min",
        timestamp=now,
        value=850.0,
        is_anomaly=True,
        score=4.2,
        lower_bound=1000.0,
        upper_bound=1500.0,
        direction="down",
        percent_deviation=-15.0,
        metadata={"window_size": "30 days"},
    )

    assert result.metric_name == "sessions_10min"
    assert result.value == 850.0
    assert result.is_anomaly is True
    assert result.score == 4.2
    assert result.direction == "down"
    assert result.percent_deviation == -15.0


def test_detection_result_minimal() -> None:
    """Test DetectionResult with only required fields."""
    now = datetime.now()
    result = DetectionResult(
        metric_name="test",
        timestamp=now,
        value=100.0,
        is_anomaly=False,
        score=0.5,
    )

    assert result.lower_bound is None
    assert result.upper_bound is None
    assert result.direction is None
    assert result.percent_deviation is None
    assert result.metadata is None


def test_alert_conditions_defaults() -> None:
    """Test AlertConditions default values."""
    conditions = AlertConditions()

    assert conditions.consecutive_anomalies == 1
    assert conditions.direction == "both"
    assert conditions.min_deviation_percent is None
    assert conditions.cooldown_minutes == 0


def test_alert_conditions_custom() -> None:
    """Test AlertConditions with custom values."""
    conditions = AlertConditions(
        consecutive_anomalies=3,
        direction="up",
        min_deviation_percent=20.0,
        cooldown_minutes=60,
    )

    assert conditions.consecutive_anomalies == 3
    assert conditions.direction == "up"
    assert conditions.min_deviation_percent == 20.0
    assert conditions.cooldown_minutes == 60


def test_check_result_creation() -> None:
    """Test CheckResult with all components."""
    now = datetime.now()
    datapoint = DataPoint(timestamp=now, value=850.0)
    detection = DetectionResult(
        metric_name="test",
        timestamp=now,
        value=850.0,
        is_anomaly=True,
        score=3.5,
    )

    result = CheckResult(
        metric_name="test",
        datapoint=datapoint,
        detection=detection,
        alert_sent=True,
        alert_reason="3 consecutive anomalies",
        errors=[],
    )

    assert result.metric_name == "test"
    assert result.datapoint == datapoint
    assert result.detection == detection
    assert result.alert_sent is True
    assert result.alert_reason == "3 consecutive anomalies"
    assert result.errors == []


def test_check_result_with_errors() -> None:
    """Test CheckResult with errors list."""
    now = datetime.now()
    datapoint = DataPoint(timestamp=now, value=850.0)
    detection = DetectionResult(
        metric_name="test",
        timestamp=now,
        value=850.0,
        is_anomaly=False,
        score=1.0,
    )

    result = CheckResult(
        metric_name="test",
        datapoint=datapoint,
        detection=detection,
        alert_sent=False,
        errors=["Storage connection failed", "Retry exhausted"],
    )

    assert len(result.errors) == 2
    assert "Storage connection failed" in result.errors
