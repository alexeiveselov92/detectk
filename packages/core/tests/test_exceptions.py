"""Tests for exception hierarchy."""

import pytest
from detectk.exceptions import (
    DetectKError,
    ConfigurationError,
    CollectionError,
    DetectionError,
    StorageError,
    AlertError,
    RegistryError,
)


def test_base_exception() -> None:
    """Test that DetectKError can be raised and caught."""
    with pytest.raises(DetectKError):
        raise DetectKError("Test error")


def test_all_exceptions_inherit_from_base() -> None:
    """Test that all custom exceptions inherit from DetectKError."""
    assert issubclass(ConfigurationError, DetectKError)
    assert issubclass(CollectionError, DetectKError)
    assert issubclass(DetectionError, DetectKError)
    assert issubclass(StorageError, DetectKError)
    assert issubclass(AlertError, DetectKError)
    assert issubclass(RegistryError, DetectKError)


def test_configuration_error_attributes() -> None:
    """Test ConfigurationError with custom attributes."""
    error = ConfigurationError(
        "Invalid config",
        config_path="/path/to/config.yaml",
        field="detector.type",
    )
    assert error.config_path == "/path/to/config.yaml"
    assert error.field == "detector.type"
    assert "Invalid config" in str(error)


def test_collection_error_attributes() -> None:
    """Test CollectionError with custom attributes."""
    error = CollectionError(
        "Query failed",
        source="clickhouse://localhost",
        query="SELECT count() FROM events",
    )
    assert error.source == "clickhouse://localhost"
    assert error.query == "SELECT count() FROM events"


def test_detection_error_attributes() -> None:
    """Test DetectionError with custom attributes."""
    error = DetectionError(
        "Insufficient data",
        metric_name="sessions_10min",
        detector_type="mad",
    )
    assert error.metric_name == "sessions_10min"
    assert error.detector_type == "mad"


def test_storage_error_attributes() -> None:
    """Test StorageError with custom attributes."""
    error = StorageError(
        "Insert failed",
        operation="save",
        table="metrics_history",
    )
    assert error.operation == "save"
    assert error.table == "metrics_history"


def test_alert_error_attributes() -> None:
    """Test AlertError with custom attributes."""
    error = AlertError(
        "Webhook failed",
        channel="mattermost",
        endpoint="https://mm.example.com/hooks/xxx",
    )
    assert error.channel == "mattermost"
    assert error.endpoint == "https://mm.example.com/hooks/xxx"


def test_registry_error_attributes() -> None:
    """Test RegistryError with custom attributes."""
    error = RegistryError(
        "Component not found",
        component_type="collector",
        component_name="clickhouse",
    )
    assert error.component_type == "collector"
    assert error.component_name == "clickhouse"


def test_catch_all_detectk_errors() -> None:
    """Test that all errors can be caught with DetectKError."""
    exceptions_to_test = [
        ConfigurationError("test"),
        CollectionError("test"),
        DetectionError("test"),
        StorageError("test"),
        AlertError("test"),
        RegistryError("test"),
    ]

    for exc in exceptions_to_test:
        with pytest.raises(DetectKError):
            raise exc
