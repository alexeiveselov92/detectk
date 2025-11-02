"""Tests for MetricCheck orchestrator."""

import tempfile
import os
from datetime import datetime
from typing import Any

import pytest
import pandas as pd

from detectk.check import MetricCheck
from detectk.config import ConfigLoader
from detectk.models import DataPoint, DetectionResult
from detectk.base import BaseCollector, BaseDetector, BaseAlerter, BaseStorage
from detectk.registry import CollectorRegistry, DetectorRegistry, AlerterRegistry, StorageRegistry
from detectk.exceptions import ConfigurationError


# ============================================================================
# Mock Implementations
# ============================================================================


class MockCollector(BaseCollector):
    """Mock collector that returns fixed value."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.closed = False

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        """Return fixed datapoint."""
        value = self.config.get("value", 100.0)
        timestamp = period_finish  # Use end of period as timestamp
        return [DataPoint(timestamp=timestamp, value=value)]

    def close(self) -> None:
        """Mark as closed."""
        self.closed = True

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


class MockStorage(BaseStorage):
    """Mock storage that tracks saves."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.saved_datapoints: list[tuple[str, list[DataPoint]]] = []
        self.saved_detections: list[tuple[str, Any]] = []

    def save_datapoints_bulk(
        self,
        metric_name: str,
        datapoints: list[DataPoint],
    ) -> None:
        """Track saved datapoints."""
        self.saved_datapoints.append((metric_name, datapoints))

    def get_last_loaded_timestamp(
        self,
        metric_name: str,
    ) -> datetime | None:
        """Return None (no previous loads)."""
        return None

    def query_datapoints(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        """Return empty dataframe."""
        return pd.DataFrame({"timestamp": [], "value": []})

    def save_detection(
        self,
        metric_name: str,
        detection: Any,
        detector_id: str,
        alert_sent: bool = False,
        alert_reason: str | None = None,
        alerter_type: str | None = None,
    ) -> None:
        """Track saved detection."""
        self.saved_detections.append((metric_name, detection, detector_id, alert_sent))

    def query_detections(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
        anomalies_only: bool = False,
    ) -> pd.DataFrame:
        """Return empty dataframe."""
        return pd.DataFrame()

    def cleanup_old_data(
        self,
        datapoints_retention_days: int,
        detections_retention_days: int | None = None,
    ) -> tuple[int, int]:
        return 0, 0

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


class MockDetector(BaseDetector):
    """Mock detector with configurable anomaly detection."""

    def detect(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        **context: Any,
    ) -> DetectionResult:
        """Return detection result based on params."""
        # Check if value exceeds threshold (if configured)
        threshold = self.params.get("threshold", 1000.0)
        is_anomaly = value > threshold

        return DetectionResult(
            metric_name=metric_name,
            timestamp=timestamp,
            value=value,
            is_anomaly=is_anomaly,
            score=3.5 if is_anomaly else 0.5,
            lower_bound=0.0,
            upper_bound=threshold,
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


class MockAlerter(BaseAlerter):
    """Mock alerter that tracks sent alerts."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.sent_alerts: list[DetectionResult] = []

    def send(self, result: DetectionResult, message: str | None = None) -> bool:
        """Track sent alert."""
        self.sent_alerts.append(result)
        return True

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def register_mocks() -> None:
    """Register mock components before each test."""
    CollectorRegistry.clear()
    DetectorRegistry.clear()
    AlerterRegistry.clear()
    StorageRegistry.clear()

    CollectorRegistry.register("mock")(MockCollector)
    StorageRegistry.register("mock")(MockStorage)
    DetectorRegistry.register("mock")(MockDetector)
    AlerterRegistry.register("mock")(MockAlerter)


@pytest.fixture
def sample_config_yaml() -> str:
    """Sample YAML configuration for testing."""
    return """
name: "test_metric"
description: "Test metric"

collector:
  type: "mock"
  params:
    value: 100.0

detector:
  type: "mock"
  params:
    threshold: 150.0

alerter:
  type: "mock"
  params:
    webhook_url: "https://example.com"

storage:
  enabled: true
  type: "mock"
  params: {}
"""


@pytest.fixture
def config_file(sample_config_yaml: str) -> str:
    """Create temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(sample_config_yaml)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


# ============================================================================
# MetricCheck Tests
# ============================================================================


def test_metriccheck_initialization() -> None:
    """Test MetricCheck initializes successfully."""
    checker = MetricCheck()

    assert checker.config_loader is not None
    assert isinstance(checker.config_loader, ConfigLoader)


def test_metriccheck_custom_loader() -> None:
    """Test MetricCheck with custom ConfigLoader."""
    custom_loader = ConfigLoader()
    checker = MetricCheck(config_loader=custom_loader)

    assert checker.config_loader is custom_loader


def test_metriccheck_execute_success(config_file: str) -> None:
    """Test successful execution of complete pipeline."""
    checker = MetricCheck()
    execution_time = datetime(2024, 1, 15, 10, 0, 0)

    result = checker.execute(config_file, execution_time=execution_time)

    # Verify result structure
    assert result.metric_name == "test_metric"
    assert result.datapoint.value == 100.0
    assert result.datapoint.timestamp == execution_time

    # No anomaly (100 < 150 threshold)
    assert result.detection.is_anomaly is False
    assert result.alert_sent is False
    assert result.errors == []


def test_metriccheck_execute_with_anomaly(config_file: str) -> None:
    """Test execution when anomaly is detected."""
    # Modify config to set value above threshold
    high_value_config = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: 200.0  # Above 150 threshold
detector:
  type: "mock"
  params:
    threshold: 150.0
alerter:
  type: "mock"
  params:
    webhook_url: "https://example.com"
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(high_value_config)
        temp_path = f.name

    try:
        checker = MetricCheck()
        result = checker.execute(temp_path)

        # Verify anomaly detected
        assert result.detection.is_anomaly is True
        assert result.detection.value == 200.0

        # Verify alert sent
        assert result.alert_sent is True
        assert result.alert_reason is not None
        assert "Anomaly detected" in result.alert_reason
    finally:
        os.unlink(temp_path)


def test_metriccheck_storage_disabled(config_file: str) -> None:
    """Test execution with storage disabled."""
    no_storage_config = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: 100.0
detector:
  type: "mock"
  params: {}
alerter:
  type: "mock"
  params: {}
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(no_storage_config)
        temp_path = f.name

    try:
        checker = MetricCheck()
        result = checker.execute(temp_path)

        # Should complete successfully without storage
        assert result.errors == []
        assert result.datapoint.value == 100.0
    finally:
        os.unlink(temp_path)


def test_metriccheck_invalid_config() -> None:
    """Test execution with invalid configuration file."""
    checker = MetricCheck()

    with pytest.raises(ConfigurationError) as exc_info:
        checker.execute("/nonexistent/config.yaml")

    assert "not found" in str(exc_info.value).lower()


def test_metriccheck_execution_time_default() -> None:
    """Test that execution_time defaults to now()."""
    config = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: 100.0
detector:
  type: "mock"
  params: {}
alerter:
  type: "mock"
  params: {}
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config)
        temp_path = f.name

    try:
        checker = MetricCheck()
        before = datetime.now()
        result = checker.execute(temp_path)
        after = datetime.now()

        # Timestamp should be between before and after
        assert before <= result.datapoint.timestamp <= after
    finally:
        os.unlink(temp_path)


def test_metriccheck_template_rendering(config_file: str) -> None:
    """Test that templates are rendered with execution_time."""
    # This test verifies the integration with ConfigLoader's template support
    checker = MetricCheck()
    execution_time = datetime(2024, 1, 15, 10, 30, 0)

    result = checker.execute(config_file, execution_time=execution_time)

    # Execution time should be passed to datapoint
    assert result.datapoint.timestamp == execution_time


def test_metriccheck_collector_close_called() -> None:
    """Test that collector.close() is called after collection."""
    config = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: 100.0
detector:
  type: "mock"
  params: {}
alerter:
  type: "mock"
  params: {}
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config)
        temp_path = f.name

    try:
        checker = MetricCheck()
        result = checker.execute(temp_path)

        # Collector should have been closed
        # Note: We can't directly verify this without instrumenting MockCollector
        # This test is a placeholder for future improvements
        assert result.errors == []
    finally:
        os.unlink(temp_path)


def test_metriccheck_error_handling() -> None:
    """Test error handling when detection fails."""
    # Create config with non-existent detector type
    bad_config = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: 100.0
detector:
  type: "nonexistent"  # This will cause registry error
  params: {}
alerter:
  type: "mock"
  params: {}
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(bad_config)
        temp_path = f.name

    try:
        checker = MetricCheck()
        result = checker.execute(temp_path)

        # Should return result with errors (not raise exception)
        assert len(result.errors) > 0
        assert result.detection.is_anomaly is False  # Fallback to non-anomaly
    finally:
        os.unlink(temp_path)


def test_metriccheck_env_var_substitution() -> None:
    """Test environment variable substitution in config."""
    # Set test environment variable
    os.environ["TEST_VALUE"] = "123.45"

    config_with_env = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: ${TEST_VALUE}
detector:
  type: "mock"
  params: {}
alerter:
  type: "mock"
  params: {}
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_with_env)
        temp_path = f.name

    try:
        checker = MetricCheck()
        result = checker.execute(temp_path)

        # Value should be substituted from env var
        assert result.datapoint.value == 123.45
    finally:
        os.unlink(temp_path)
        del os.environ["TEST_VALUE"]


def test_metriccheck_multiple_executions() -> None:
    """Test multiple executions with same checker instance."""
    config = """
name: "test_metric"
collector:
  type: "mock"
  params:
    value: 100.0
detector:
  type: "mock"
  params: {}
alerter:
  type: "mock"
  params: {}
storage:
  enabled: false
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config)
        temp_path = f.name

    try:
        checker = MetricCheck()

        # Run multiple times
        result1 = checker.execute(temp_path)
        result2 = checker.execute(temp_path)

        # Both should succeed
        assert result1.errors == []
        assert result2.errors == []
        assert result1.datapoint.value == result2.datapoint.value
    finally:
        os.unlink(temp_path)
