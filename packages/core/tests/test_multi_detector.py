"""Tests for multi-detector configuration and auto-generated IDs."""

import pytest
from detectk.config.models import (
    DetectorConfig,
    MetricConfig,
    CollectorConfig,
    AlerterConfig,
    DETECTOR_DEFAULTS,
)


def test_detector_config_auto_id_generation() -> None:
    """Test that detector ID is auto-generated when not provided."""
    detector = DetectorConfig(type="mad", params={"window_size": "30 days"})

    assert detector.id is not None
    assert len(detector.id) == 8  # 8-char hash
    assert detector.id.isalnum()  # Only alphanumeric characters


def test_detector_config_manual_id() -> None:
    """Test that manual ID is preserved."""
    detector = DetectorConfig(
        id="my_custom_id",
        type="mad",
        params={"window_size": "30 days"}
    )

    assert detector.id == "my_custom_id"


def test_detector_config_id_deterministic() -> None:
    """Test that same type + params generate same ID."""
    detector1 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 5.0}
    )
    detector2 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 5.0}
    )

    assert detector1.id == detector2.id


def test_detector_config_id_parameter_order_independent() -> None:
    """Test that parameter order doesn't affect generated ID."""
    detector1 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 5.0}
    )
    detector2 = DetectorConfig(
        type="mad",
        params={"n_sigma": 5.0, "window_size": "30 days"}  # Different order
    )

    assert detector1.id == detector2.id


def test_detector_config_id_different_params() -> None:
    """Test that different params generate different IDs."""
    detector1 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 3.0}
    )
    detector2 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 5.0}
    )

    assert detector1.id != detector2.id


def test_detector_config_id_different_types() -> None:
    """Test that different types generate different IDs."""
    detector1 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days"}
    )
    detector2 = DetectorConfig(
        type="zscore",
        params={"window_size": "30 days"}
    )

    assert detector1.id != detector2.id


def test_detector_config_id_normalization_with_defaults() -> None:
    """Test that default values are normalized away from ID calculation."""
    # MAD detector has default n_sigma=3.0
    detector1 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 3.0}  # Explicit default
    )
    detector2 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days"}  # Implicit default
    )

    # Should generate same ID because n_sigma=3.0 is default
    assert detector1.id == detector2.id


def test_detector_config_id_normalization_non_default() -> None:
    """Test that non-default values are included in ID."""
    detector1 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days"}  # Uses default n_sigma=3.0
    )
    detector2 = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 5.0}  # Non-default
    )

    # Should generate different IDs
    assert detector1.id != detector2.id


def test_detector_config_invalid_id_format() -> None:
    """Test that invalid ID format raises error."""
    with pytest.raises(ValueError, match="contains invalid characters"):
        DetectorConfig(
            id="invalid id with spaces",
            type="mad",
            params={}
        )


def test_detector_config_empty_id() -> None:
    """Test that empty string ID raises error."""
    with pytest.raises(ValueError, match="cannot be empty"):
        DetectorConfig(
            id="",
            type="mad",
            params={}
        )


def test_metric_config_single_detector() -> None:
    """Test that single detector config works as before."""
    config = MetricConfig(
        name="test_metric",
        collector=CollectorConfig(type="clickhouse", params={}),
        detector=DetectorConfig(type="mad", params={"window_size": "30 days"}),
        alerter=AlerterConfig(type="mattermost", params={}),
    )

    # Single detector should populate both fields
    assert config.detector is not None
    assert config.detectors is not None
    assert len(config.detectors) == 1
    assert config.detectors[0] == config.detector


def test_metric_config_multiple_detectors() -> None:
    """Test multiple detectors configuration."""
    config = MetricConfig(
        name="test_metric",
        collector=CollectorConfig(type="clickhouse", params={}),
        detectors=[
            DetectorConfig(type="mad", params={"window_size": "30 days", "n_sigma": 3.0}),
            DetectorConfig(type="mad", params={"window_size": "30 days", "n_sigma": 5.0}),
            DetectorConfig(type="zscore", params={"window_size": "7 days"}),
        ],
        alerter=AlerterConfig(type="mattermost", params={}),
    )

    assert config.detector is None  # Ambiguous which one to use
    assert config.detectors is not None
    assert len(config.detectors) == 3

    # All detectors should have auto-generated IDs
    assert all(d.id is not None for d in config.detectors)

    # All IDs should be unique
    detector_ids = [d.id for d in config.detectors]
    assert len(detector_ids) == len(set(detector_ids))


def test_metric_config_duplicate_detector_ids() -> None:
    """Test that duplicate detector IDs are rejected."""
    with pytest.raises(ValueError, match="Duplicate detector IDs"):
        MetricConfig(
            name="test_metric",
            collector=CollectorConfig(type="clickhouse", params={}),
            detectors=[
                DetectorConfig(id="same_id", type="mad", params={"n_sigma": 3.0}),
                DetectorConfig(id="same_id", type="mad", params={"n_sigma": 5.0}),
            ],
            alerter=AlerterConfig(type="mattermost", params={}),
        )


def test_metric_config_both_detector_and_detectors() -> None:
    """Test that providing both detector and detectors raises error."""
    with pytest.raises(ValueError, match="Cannot specify both"):
        MetricConfig(
            name="test_metric",
            collector=CollectorConfig(type="clickhouse", params={}),
            detector=DetectorConfig(type="mad", params={}),
            detectors=[
                DetectorConfig(type="mad", params={"n_sigma": 3.0}),
            ],
            alerter=AlerterConfig(type="mattermost", params={}),
        )


def test_metric_config_neither_detector_nor_detectors() -> None:
    """Test that missing both detector and detectors raises error."""
    with pytest.raises(ValueError, match="Either 'detector' or 'detectors' must be provided"):
        MetricConfig(
            name="test_metric",
            collector=CollectorConfig(type="clickhouse", params={}),
            alerter=AlerterConfig(type="mattermost", params={}),
        )


def test_metric_config_empty_detectors_list() -> None:
    """Test that empty detectors list raises error."""
    with pytest.raises(ValueError, match="'detectors' list cannot be empty"):
        MetricConfig(
            name="test_metric",
            collector=CollectorConfig(type="clickhouse", params={}),
            detectors=[],
            alerter=AlerterConfig(type="mattermost", params={}),
        )


def test_metric_config_get_detectors_single() -> None:
    """Test get_detectors() method with single detector."""
    config = MetricConfig(
        name="test_metric",
        collector=CollectorConfig(type="clickhouse", params={}),
        detector=DetectorConfig(type="mad", params={}),
        alerter=AlerterConfig(type="mattermost", params={}),
    )

    detectors = config.get_detectors()
    assert len(detectors) == 1
    assert detectors[0].type == "mad"


def test_metric_config_get_detectors_multiple() -> None:
    """Test get_detectors() method with multiple detectors."""
    config = MetricConfig(
        name="test_metric",
        collector=CollectorConfig(type="clickhouse", params={}),
        detectors=[
            DetectorConfig(type="mad", params={"n_sigma": 3.0}),
            DetectorConfig(type="zscore", params={}),
        ],
        alerter=AlerterConfig(type="mattermost", params={}),
    )

    detectors = config.get_detectors()
    assert len(detectors) == 2
    assert detectors[0].type == "mad"
    assert detectors[1].type == "zscore"


def test_detector_defaults_registry() -> None:
    """Test that DETECTOR_DEFAULTS registry is populated."""
    assert "threshold" in DETECTOR_DEFAULTS
    assert "mad" in DETECTOR_DEFAULTS
    assert "zscore" in DETECTOR_DEFAULTS

    # Test specific defaults
    assert DETECTOR_DEFAULTS["mad"]["n_sigma"] == 3.0
    assert DETECTOR_DEFAULTS["zscore"]["n_sigma"] == 3.0
    assert DETECTOR_DEFAULTS["threshold"]["operator"] == "greater_than"


def test_detector_config_normalize_params() -> None:
    """Test parameter normalization logic."""
    detector = DetectorConfig(
        type="mad",
        params={"window_size": "30 days", "n_sigma": 3.0, "seasonal_features": []}
    )

    normalized = detector._normalize_params()

    # All params with default values should be removed
    assert "n_sigma" not in normalized  # Default is 3.0
    assert "seasonal_features" not in normalized  # Default is []
    assert "window_size" in normalized  # No default for this


def test_detector_config_hash_consistency() -> None:
    """Test that hash generation is consistent across multiple creations."""
    params = {"window_size": "30 days", "n_sigma": 5.0}

    ids = []
    for _ in range(10):
        detector = DetectorConfig(type="mad", params=params.copy())
        ids.append(detector.id)

    # All IDs should be identical
    assert len(set(ids)) == 1
