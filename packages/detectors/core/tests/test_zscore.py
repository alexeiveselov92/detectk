"""Tests for Z-Score detector."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from detectk.exceptions import DetectionError
from detectk_detectors.zscore import ZScoreDetector


def test_zscore_detector_registration() -> None:
    """Test that ZScoreDetector is registered in DetectorRegistry."""
    from detectk.registry.detector import DetectorRegistry

    assert DetectorRegistry.is_registered("zscore")
    detector_class = DetectorRegistry.get("zscore")
    assert detector_class == ZScoreDetector


def test_zscore_detector_initialization() -> None:
    """Test ZScoreDetector initialization with default parameters."""
    detector = ZScoreDetector(storage=None, window_size="7 days")

    assert detector.window_size == "7 days"
    assert detector.n_sigma == 3.0
    assert detector.use_weighted is True
    assert detector.exp_decay_factor == 0.1
    assert detector.seasonal_features == []
    assert detector.use_combined_seasonality is False


def test_zscore_detector_custom_params() -> None:
    """Test ZScoreDetector with custom parameters."""
    detector = ZScoreDetector(
        storage=None,
        window_size="14 days",
        n_sigma=2.5,
        use_weighted=False,
        exp_decay_factor=0.2,
        seasonal_features=["hour_of_day"],
        use_combined_seasonality=True,
    )

    assert detector.window_size == "14 days"
    assert detector.n_sigma == 2.5
    assert detector.use_weighted is False
    assert detector.exp_decay_factor == 0.2
    assert detector.seasonal_features == ["hour_of_day"]
    assert detector.use_combined_seasonality is True


def test_zscore_detector_invalid_n_sigma() -> None:
    """Test that negative n_sigma raises error."""
    with pytest.raises(DetectionError, match="n_sigma must be positive"):
        ZScoreDetector(storage=None, n_sigma=-1.0)


def test_zscore_detector_invalid_exp_decay() -> None:
    """Test that negative exp_decay_factor raises error."""
    with pytest.raises(DetectionError, match="exp_decay_factor must be positive"):
        ZScoreDetector(storage=None, exp_decay_factor=-0.1)


def test_zscore_detector_invalid_seasonal_features() -> None:
    """Test that non-list seasonal_features raises error."""
    with pytest.raises(DetectionError, match="seasonal_features must be a list"):
        ZScoreDetector(storage=None, seasonal_features="hour_of_day")  # type: ignore


def test_zscore_detector_no_storage() -> None:
    """Test that detection without storage raises error."""
    detector = ZScoreDetector(storage=None)

    with pytest.raises(DetectionError, match="ZScoreDetector requires storage"):
        detector.detect("test_metric", 100.0, datetime.now())


def test_zscore_detector_empty_history() -> None:
    """Test detection with empty historical data."""
    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame()

    detector = ZScoreDetector(storage=mock_storage)

    with pytest.raises(DetectionError, match="No historical data found"):
        detector.detect("test_metric", 100.0, datetime.now())


def test_zscore_detector_insufficient_data() -> None:
    """Test detection with insufficient historical data."""
    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": [datetime.now(), datetime.now()],
            "value": [100.0, 110.0],
        }
    )

    detector = ZScoreDetector(storage=mock_storage)

    with pytest.raises(DetectionError, match="Insufficient data.*minimum 3 required"):
        detector.detect("test_metric", 100.0, datetime.now())


def test_zscore_detector_simple_no_anomaly() -> None:
    """Test Z-score detection with no anomaly."""
    # Historical data: mean=100, std~3.16
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(len(historical_values))]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, window_size="5 hours", use_weighted=False)

    # Current value 103 is within mean ± 3*std
    result = detector.detect("test_metric", 103.0, datetime.now())

    assert result.is_anomaly is False
    assert result.metric_name == "test_metric"
    assert result.value == 103.0
    assert result.score < 3.0  # Less than n_sigma threshold
    assert result.direction is None


def test_zscore_detector_simple_with_anomaly() -> None:
    """Test Z-score detection with anomaly."""
    # Historical data: mean=100, std~3.16
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(len(historical_values))]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, window_size="5 hours", use_weighted=False)

    # Current value 150 is far above mean + 3*std
    result = detector.detect("test_metric", 150.0, datetime.now())

    assert result.is_anomaly is True
    assert result.direction == "up"
    assert result.score > 3.0
    assert result.value > result.upper_bound


def test_zscore_detector_downward_anomaly() -> None:
    """Test Z-score detection with downward anomaly."""
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(5)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, use_weighted=False)

    # Value 50 is far below mean - 3*std
    result = detector.detect("test_metric", 50.0, datetime.now())

    assert result.is_anomaly is True
    assert result.direction == "down"
    assert result.value < result.lower_bound


def test_zscore_detector_with_identical_values() -> None:
    """Test Z-score when all historical values identical."""
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, use_weighted=False)

    # Value matches exactly
    result = detector.detect("test_metric", 100.0, datetime.now())

    assert result.is_anomaly is False
    assert result.score == 0.0
    assert result.metadata["std"] == 0.0

    # Value is different
    result_anomaly = detector.detect("test_metric", 101.0, datetime.now())

    assert result_anomaly.is_anomaly is True
    assert result_anomaly.score == float("inf")  # std=0, any deviation is infinite


def test_zscore_weighted_mean_std() -> None:
    """Test weighted mean and std calculation."""
    detector = ZScoreDetector(storage=None, use_weighted=False)

    data = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    weights = np.ones(5) / 5  # Equal weights

    mean, std = detector._weighted_mean_std(data, weights)

    # Mean should be 30.0
    assert abs(mean - 30.0) < 0.1
    # Std should be ~14.14
    assert abs(std - 14.14) < 0.5


def test_zscore_compute_weights_unweighted() -> None:
    """Test that unweighted mode returns equal weights."""
    detector = ZScoreDetector(storage=None, use_weighted=False)

    weights = detector._compute_weights(10)

    assert len(weights) == 10
    assert np.allclose(weights, 0.1)
    assert abs(weights.sum() - 1.0) < 1e-10


def test_zscore_compute_weights_exponential() -> None:
    """Test exponential decay weights."""
    detector = ZScoreDetector(storage=None, use_weighted=True, exp_decay_factor=0.5)

    weights = detector._compute_weights(5)

    assert len(weights) == 5
    assert abs(weights.sum() - 1.0) < 1e-10
    # Recent values should have higher weight
    assert weights[-1] > weights[0]


def test_zscore_percent_deviation() -> None:
    """Test percent deviation calculation."""
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, use_weighted=False)

    # 120 is 20% above 100
    result = detector.detect("test_metric", 120.0, datetime.now())

    assert result.percent_deviation is not None
    assert abs(result.percent_deviation - 20.0) < 0.1


def test_zscore_metadata() -> None:
    """Test that detection result includes comprehensive metadata."""
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(5)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, use_weighted=True)

    result = detector.detect("test_metric", 100.0, datetime.now())

    assert "detector" in result.metadata
    assert result.metadata["detector"] == "zscore"
    assert "window_size" in result.metadata
    assert "n_sigma" in result.metadata
    assert "mean" in result.metadata
    assert "std" in result.metadata
    assert "use_weighted" in result.metadata
    assert "seasonal_features" in result.metadata
    assert "window_points" in result.metadata


def test_zscore_seasonal_missing_context_column() -> None:
    """Test error when seasonal features requested but context column missing."""
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, seasonal_features=["hour_of_day"])

    with pytest.raises(DetectionError, match="context.*column missing"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=14)


def test_zscore_seasonal_feature_not_in_current_context() -> None:
    """Test error when seasonal feature missing from current context."""
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]
    contexts = [{"hour_of_day": 14}] * 10

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, seasonal_features=["hour_of_day", "day_of_week"])

    with pytest.raises(DetectionError, match="Seasonal features.*not found in current context"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=14)


def test_zscore_seasonal_separate_grouping() -> None:
    """Test separate seasonal grouping (union of groups)."""
    # Add variation to avoid std=0
    historical_values = [95.0, 200.0, 98.0, 205.0, 102.0, 195.0, 100.0, 210.0, 101.0, 198.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]
    contexts = [{"hour_of_day": i % 2} for i in range(10)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = ZScoreDetector(
        storage=mock_storage,
        seasonal_features=["hour_of_day"],
        use_combined_seasonality=False,
        use_weighted=False,
    )

    # hour_of_day=0 should match values around 95-102
    result = detector.detect("test_metric", 105.0, datetime.now(), hour_of_day=0)

    assert result.is_anomaly is False
    # Mean should be around 99
    assert 95.0 <= result.metadata["mean"] <= 105.0


def test_zscore_seasonal_combined_grouping() -> None:
    """Test combined seasonal grouping (intersection of features)."""
    historical_values = [98.0, 102.0, 100.0, 105.0, 95.0, 200.0, 205.0, 195.0, 210.0, 198.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]
    contexts = [
        {"hour_of_day": 14, "day_of_week": 1},
        {"hour_of_day": 14, "day_of_week": 1},
        {"hour_of_day": 14, "day_of_week": 1},
        {"hour_of_day": 14, "day_of_week": 2},
        {"hour_of_day": 15, "day_of_week": 1},
        {"hour_of_day": 15, "day_of_week": 2},
        {"hour_of_day": 15, "day_of_week": 2},
        {"hour_of_day": 16, "day_of_week": 1},
        {"hour_of_day": 16, "day_of_week": 2},
        {"hour_of_day": 16, "day_of_week": 2},
    ]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = ZScoreDetector(
        storage=mock_storage,
        seasonal_features=["hour_of_day", "day_of_week"],
        use_combined_seasonality=True,
        use_weighted=False,
    )

    # hour=14 AND dow=1 should match first 3 points: 98, 102, 100
    result = detector.detect("test_metric", 101.0, datetime.now(), hour_of_day=14, day_of_week=1)

    # With std=1.63 and mean=100, value=101 should not be anomalous (within 1 sigma)
    # Mean should be 100
    assert 98.0 <= result.metadata["mean"] <= 102.0
    assert result.metadata["std"] < 3.0  # Low std due to similar values


def test_zscore_seasonal_no_matching_group() -> None:
    """Test error when no historical data matches seasonal group."""
    historical_values = [100.0] * 5
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(5)]
    contexts = [{"hour_of_day": 10}] * 5

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, seasonal_features=["hour_of_day"], use_weighted=False)

    with pytest.raises(DetectionError, match="No historical data found for seasonal group"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=14)


def test_zscore_seasonal_insufficient_data_in_group() -> None:
    """Test error when seasonal group has insufficient data."""
    historical_values = [100.0, 200.0, 100.0, 200.0, 100.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(5)]
    contexts = [{"hour_of_day": i % 3} for i in range(5)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = ZScoreDetector(storage=mock_storage, seasonal_features=["hour_of_day"], use_weighted=False)

    # hour=2 has only 1 point
    with pytest.raises(DetectionError, match="Insufficient data in seasonal group.*minimum 3"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=2)
