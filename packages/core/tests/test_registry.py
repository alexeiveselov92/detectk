"""Tests for component registry."""

import pytest
from typing import Any
from datetime import datetime

from detectk.registry import (
    CollectorRegistry,
    DetectorRegistry,
    AlerterRegistry,
    StorageRegistry,
)
from detectk.base import BaseCollector, BaseDetector, BaseAlerter, BaseStorage
from detectk.models import DataPoint, DetectionResult
from detectk.exceptions import RegistryError
import pandas as pd


# Mock implementations for testing
class MockCollector(BaseCollector):
    """Mock collector for testing."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        return [DataPoint(timestamp=datetime.now(), value=123.45)]

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


class MockStorage(BaseStorage):
    """Mock storage for testing."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def save_datapoints_bulk(
        self,
        metric_name: str,
        datapoints: list[DataPoint],
    ) -> None:
        pass

    def get_last_loaded_timestamp(
        self,
        metric_name: str,
    ) -> datetime | None:
        return None

    def query_datapoints(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def save_detection(
        self,
        metric_name: str,
        detection: DetectionResult,
        detector_id: str,
        alert_sent: bool = False,
        alert_reason: str | None = None,
        alerter_type: str | None = None,
    ) -> None:
        pass

    def query_detections(
        self,
        metric_name: str,
        window: str | int,
        end_time: datetime | None = None,
        anomalies_only: bool = False,
    ) -> pd.DataFrame:
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
    """Mock detector for testing."""

    def detect(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        **context: Any,
    ) -> DetectionResult:
        return DetectionResult(
            metric_name=metric_name,
            timestamp=timestamp,
            value=value,
            is_anomaly=False,
            score=0.0,
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


class MockAlerter(BaseAlerter):
    """Mock alerter for testing."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def send(self, result: DetectionResult, message: str | None = None) -> bool:
        return True

    def validate_config(self, config: dict[str, Any]) -> None:
        pass


@pytest.fixture(autouse=True)
def cleanup_registries() -> None:
    """Clear registries before each test."""
    CollectorRegistry.clear()
    DetectorRegistry.clear()
    AlerterRegistry.clear()
    StorageRegistry.clear()


def test_collector_registry_register() -> None:
    """Test registering a collector."""

    @CollectorRegistry.register("test")
    class TestCollector(MockCollector):
        pass

    assert CollectorRegistry.is_registered("test")
    assert "test" in CollectorRegistry.list_all()


def test_collector_registry_get() -> None:
    """Test getting registered collector."""

    @CollectorRegistry.register("test")
    class TestCollector(MockCollector):
        pass

    collector_class = CollectorRegistry.get("test")
    assert collector_class == TestCollector


def test_collector_registry_create() -> None:
    """Test creating collector instance."""

    @CollectorRegistry.register("test")
    class TestCollector(MockCollector):
        pass

    config = {"host": "localhost"}
    collector = CollectorRegistry.create("test", config)

    assert isinstance(collector, MockCollector)
    assert collector.config == config


def test_registry_get_not_found() -> None:
    """Test getting non-existent component raises error."""
    with pytest.raises(RegistryError) as exc_info:
        CollectorRegistry.get("nonexistent")

    assert "not found" in str(exc_info.value).lower()
    assert "nonexistent" in str(exc_info.value)


def test_registry_duplicate_registration() -> None:
    """Test registering same name twice raises error."""

    @CollectorRegistry.register("test")
    class TestCollector1(MockCollector):
        pass

    with pytest.raises(RegistryError) as exc_info:

        @CollectorRegistry.register("test")
        class TestCollector2(MockCollector):
            pass

    assert "already registered" in str(exc_info.value).lower()


def test_registry_list_all() -> None:
    """Test listing all registered components."""

    @CollectorRegistry.register("collector1")
    class TestCollector1(MockCollector):
        pass

    @CollectorRegistry.register("collector2")
    class TestCollector2(MockCollector):
        pass

    all_collectors = CollectorRegistry.list_all()
    assert all_collectors == ["collector1", "collector2"]  # Sorted


def test_detector_registry() -> None:
    """Test detector registry works independently."""

    @DetectorRegistry.register("test_detector")
    class TestDetector(MockDetector):
        pass

    assert DetectorRegistry.is_registered("test_detector")
    assert not CollectorRegistry.is_registered("test_detector")  # Different registry


def test_alerter_registry() -> None:
    """Test alerter registry."""

    @AlerterRegistry.register("test_alerter")
    class TestAlerter(MockAlerter):
        pass

    alerter = AlerterRegistry.create("test_alerter", {"webhook": "http://test"})
    assert isinstance(alerter, MockAlerter)


def test_storage_registry() -> None:
    """Test storage registry."""

    @StorageRegistry.register("test_storage")
    class TestStorage(MockStorage):
        pass

    storage = StorageRegistry.create("test_storage", {"connection": "test"})
    assert isinstance(storage, MockStorage)


def test_registry_error_attributes() -> None:
    """Test RegistryError includes component info."""
    with pytest.raises(RegistryError) as exc_info:
        CollectorRegistry.get("missing")

    error = exc_info.value
    assert error.component_type == "collector"
    assert error.component_name == "missing"


def test_multiple_components_same_registry() -> None:
    """Test registering multiple components in same registry."""

    @CollectorRegistry.register("clickhouse")
    class ClickHouseCollector(MockCollector):
        pass

    @CollectorRegistry.register("postgres")
    class PostgresCollector(MockCollector):
        pass

    @CollectorRegistry.register("http")
    class HTTPCollector(MockCollector):
        pass

    all_collectors = CollectorRegistry.list_all()
    assert len(all_collectors) == 3
    assert set(all_collectors) == {"clickhouse", "postgres", "http"}


def test_registry_clear() -> None:
    """Test clearing registry."""

    @CollectorRegistry.register("test")
    class TestCollector(MockCollector):
        pass

    assert len(CollectorRegistry.list_all()) == 1

    CollectorRegistry.clear()

    assert len(CollectorRegistry.list_all()) == 0
    assert not CollectorRegistry.is_registered("test")
