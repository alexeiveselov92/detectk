"""Tests for MissingDataDetector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from detectk_detectors.missing_data import MissingDataDetector
from detectk.models import DetectionResult


class TestMissingDataDetector:
    """Test suite for MissingDataDetector."""

    def test_missing_data_single_point(self):
        """Test detection of single missing data point."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=1  # Alert on first missing
        )

        result = detector.detect(
            metric_name="test_metric",
            value=None,
            timestamp=datetime.now(),
            is_missing=True
        )

        assert result.is_anomaly is True
        assert result.direction == "missing"
        assert result.value is None
        assert result.metadata["consecutive_missing"] == 1

    def test_missing_data_consecutive_threshold(self):
        """Test that detector requires consecutive missing points."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=3  # Require 3 consecutive
        )

        metric_name = "test_metric"
        now = datetime.now()

        # First missing - should NOT alert
        result1 = detector.detect(
            metric_name=metric_name,
            value=None,
            timestamp=now,
            is_missing=True
        )
        assert result1.is_anomaly is False
        assert result1.metadata["consecutive_missing"] == 1

        # Second missing - should NOT alert
        result2 = detector.detect(
            metric_name=metric_name,
            value=None,
            timestamp=now + timedelta(minutes=10),
            is_missing=True
        )
        assert result2.is_anomaly is False
        assert result2.metadata["consecutive_missing"] == 2

        # Third missing - should ALERT
        result3 = detector.detect(
            metric_name=metric_name,
            value=None,
            timestamp=now + timedelta(minutes=20),
            is_missing=True
        )
        assert result3.is_anomaly is True
        assert result3.metadata["consecutive_missing"] == 3

    def test_missing_count_resets_on_data_arrival(self):
        """Test that missing count resets when data arrives."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=3
        )

        metric_name = "test_metric"
        now = datetime.now()

        # Two missing points
        detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)
        detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)

        # Data arrives - should reset count
        result = detector.detect(
            metric_name=metric_name,
            value=100.0,
            timestamp=now + timedelta(minutes=20)
        )
        assert result.is_anomaly is False

        # Next missing should start count from 1
        result_missing = detector.detect(
            metric_name=metric_name,
            value=None,
            timestamp=now + timedelta(minutes=30),
            is_missing=True
        )
        assert result_missing.metadata["consecutive_missing"] == 1

    def test_staleness_detection(self):
        """Test detection of stale data."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=1,
            max_staleness_minutes=15
        )

        now = datetime.now()
        last_known = now - timedelta(minutes=30)  # 30 minutes old

        result = detector.detect(
            metric_name="test_metric",
            value=100.0,
            timestamp=now,
            last_known_timestamp=last_known
        )

        assert result.is_anomaly is True
        assert result.direction == "stale"
        assert result.metadata["staleness_minutes"] == 30.0
        assert result.metadata["max_staleness_minutes"] == 15

    def test_fresh_data_not_stale(self):
        """Test that fresh data is not considered stale."""
        detector = MissingDataDetector(
            storage=Mock(),
            max_staleness_minutes=15
        )

        now = datetime.now()
        last_known = now - timedelta(minutes=5)  # 5 minutes old (fresh)

        result = detector.detect(
            metric_name="test_metric",
            value=100.0,
            timestamp=now,
            last_known_timestamp=last_known
        )

        assert result.is_anomaly is False

    def test_treat_zero_as_missing(self):
        """Test treating zero values as missing."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=1,
            treat_zero_as_missing=True
        )

        result = detector.detect(
            metric_name="test_metric",
            value=0.0,
            timestamp=datetime.now()
        )

        assert result.is_anomaly is True
        assert result.direction == "missing"

    def test_zero_not_treated_as_missing_by_default(self):
        """Test that zero is normal value by default."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=1,
            treat_zero_as_missing=False  # Default
        )

        result = detector.detect(
            metric_name="test_metric",
            value=0.0,
            timestamp=datetime.now()
        )

        assert result.is_anomaly is False

    def test_multiple_metrics_tracked_separately(self):
        """Test that different metrics have independent missing counts."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=2
        )

        now = datetime.now()

        # Metric A - 1 missing
        detector.detect(metric_name="metric_a", value=None, timestamp=now, is_missing=True)

        # Metric B - 1 missing
        result_b = detector.detect(metric_name="metric_b", value=None, timestamp=now, is_missing=True)

        # Both should be at count=1, not alerting
        assert result_b.is_anomaly is False
        assert result_b.metadata["consecutive_missing"] == 1

        # Metric A - 2nd missing (should alert)
        result_a = detector.detect(metric_name="metric_a", value=None, timestamp=now, is_missing=True)
        assert result_a.is_anomaly is True
        assert result_a.metadata["consecutive_missing"] == 2

    def test_reset_missing_count(self):
        """Test manual reset of missing count."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=3
        )

        metric_name = "test_metric"
        now = datetime.now()

        # Two missing points
        detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)
        detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)

        # Manual reset
        detector.reset_missing_count(metric_name)

        # Next missing should start from 1 again
        result = detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)
        assert result.metadata["consecutive_missing"] == 1

    def test_anomaly_score_calculation(self):
        """Test that anomaly score reflects progress towards threshold."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=5
        )

        metric_name = "test_metric"
        now = datetime.now()

        # 2 out of 5 missing
        result = detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)
        result = detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)

        assert result.score == pytest.approx(2.0 / 5.0)  # 40%

        # 5 out of 5 missing (threshold reached)
        for _ in range(3):
            result = detector.detect(metric_name=metric_name, value=None, timestamp=now, is_missing=True)

        assert result.score == pytest.approx(5.0 / 5.0)  # 100%
        assert result.is_anomaly is True

    def test_normal_data_returns_zero_score(self):
        """Test that normal data has zero anomaly score."""
        detector = MissingDataDetector(storage=Mock())

        result = detector.detect(
            metric_name="test_metric",
            value=100.0,
            timestamp=datetime.now()
        )

        assert result.score == 0.0
        assert result.is_anomaly is False

    def test_explicit_is_missing_flag(self):
        """Test detection using explicit is_missing flag from context."""
        detector = MissingDataDetector(storage=Mock(), consecutive_missing=1)

        # Even with non-None value, is_missing flag takes precedence
        result = detector.detect(
            metric_name="test_metric",
            value=0.0,  # Has value
            timestamp=datetime.now(),
            is_missing=True  # But explicitly marked as missing
        )

        assert result.is_anomaly is True
        assert result.direction == "missing"

    def test_detector_metadata_included(self):
        """Test that detection results include detector metadata."""
        detector = MissingDataDetector(
            storage=Mock(),
            consecutive_missing=2,
            max_staleness_minutes=30
        )

        result = detector.detect(
            metric_name="test_metric",
            value=100.0,
            timestamp=datetime.now()
        )

        assert "detector" in result.metadata
        assert result.metadata["detector"] == "missing_data"
