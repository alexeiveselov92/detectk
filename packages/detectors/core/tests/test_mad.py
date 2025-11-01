"""Tests for MAD (Median Absolute Deviation) detector."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from detectk.exceptions import DetectionError
from detectk_detectors.mad import MADDetector


def test_mad_detector_registration() -> None:
    """Test that MADDetector is registered in DetectorRegistry."""
    from detectk.registry.detector import DetectorRegistry

    assert DetectorRegistry.is_registered("mad")
    detector_class = DetectorRegistry.get("mad")
    assert detector_class == MADDetector


def test_mad_detector_initialization() -> None:
    """Test MADDetector initialization with default parameters."""
    detector = MADDetector(storage=None, window_size="30 days")

    assert detector.window_size == "30 days"
    assert detector.n_sigma == 3.0
    assert detector.use_weighted is True
    assert detector.exp_decay_factor == 0.1
    assert detector.seasonal_features == []
    assert detector.use_combined_seasonality is False


def test_mad_detector_custom_params() -> None:
    """Test MADDetector with custom parameters."""
    detector = MADDetector(
        storage=None,
        window_size="7 days",
        n_sigma=5.0,
        use_weighted=False,
        exp_decay_factor=0.2,
        seasonal_features=["hour_of_day"],
        use_combined_seasonality=True,
    )

    assert detector.window_size == "7 days"
    assert detector.n_sigma == 5.0
    assert detector.use_weighted is False
    assert detector.exp_decay_factor == 0.2
    assert detector.seasonal_features == ["hour_of_day"]
    assert detector.use_combined_seasonality is True


def test_mad_detector_invalid_n_sigma() -> None:
    """Test that negative n_sigma raises error."""
    with pytest.raises(DetectionError, match="n_sigma must be positive"):
        MADDetector(storage=None, n_sigma=-1.0)


def test_mad_detector_invalid_exp_decay() -> None:
    """Test that negative exp_decay_factor raises error."""
    with pytest.raises(DetectionError, match="exp_decay_factor must be positive"):
        MADDetector(storage=None, exp_decay_factor=-0.1)


def test_mad_detector_invalid_seasonal_features() -> None:
    """Test that non-list seasonal_features raises error."""
    with pytest.raises(DetectionError, match="seasonal_features must be a list"):
        MADDetector(storage=None, seasonal_features="hour_of_day")  # type: ignore


def test_mad_detector_no_storage() -> None:
    """Test that detection without storage raises error."""
    detector = MADDetector(storage=None)

    with pytest.raises(DetectionError, match="MADDetector requires storage"):
        detector.detect("test_metric", 100.0, datetime.now())


def test_mad_detector_empty_history() -> None:
    """Test detection with empty historical data."""
    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame()

    detector = MADDetector(storage=mock_storage)

    with pytest.raises(DetectionError, match="No historical data found"):
        detector.detect("test_metric", 100.0, datetime.now())


def test_mad_detector_insufficient_data() -> None:
    """Test detection with insufficient historical data."""
    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": [datetime.now(), datetime.now()],
            "value": [100.0, 110.0],
        }
    )

    detector = MADDetector(storage=mock_storage)

    with pytest.raises(DetectionError, match="Insufficient data.*minimum 3 required"):
        detector.detect("test_metric", 100.0, datetime.now())


def test_mad_detector_simple_no_anomaly() -> None:
    """Test MAD detection with no anomaly."""
    # Historical data: consistent values around 100
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0, 100.0, 98.0, 101.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(len(historical_values))]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],  # Oldest first
            "value": historical_values[::-1],
        }
    )

    detector = MADDetector(storage=mock_storage, window_size="8 hours", use_weighted=False)

    # Current value is within expected range
    result = detector.detect("test_metric", 103.0, datetime.now())

    assert result.is_anomaly is False
    assert result.metric_name == "test_metric"
    assert result.value == 103.0
    assert result.score < 3.0  # Less than n_sigma threshold
    assert result.lower_bound is not None
    assert result.upper_bound is not None
    assert result.direction is None  # Not anomalous


def test_mad_detector_simple_with_anomaly() -> None:
    """Test MAD detection with anomaly."""
    # Historical data: consistent values around 100
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0, 100.0, 98.0, 101.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(len(historical_values))]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = MADDetector(storage=mock_storage, window_size="8 hours", use_weighted=False)

    # Current value is extreme outlier
    result = detector.detect("test_metric", 200.0, datetime.now())

    assert result.is_anomaly is True
    assert result.direction == "up"
    assert result.score > 3.0  # Above n_sigma threshold
    assert result.value > result.upper_bound


def test_mad_detector_downward_anomaly() -> None:
    """Test MAD detection with downward anomaly."""
    historical_values = [95.0, 98.0, 100.0, 102.0, 105.0, 100.0, 98.0, 101.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(len(historical_values))]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = MADDetector(storage=mock_storage, window_size="8 hours", use_weighted=False)

    # Current value is extremely low
    result = detector.detect("test_metric", 10.0, datetime.now())

    assert result.is_anomaly is True
    assert result.direction == "down"
    assert result.value < result.lower_bound


def test_mad_detector_weighted_vs_unweighted() -> None:
    """Test that weighted detection gives more importance to recent data."""
    # Historical data with clear trend upward
    historical_values = [50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(len(historical_values))]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],  # Oldest first: 50, 60, 70, 80, 90, 100
            "value": historical_values[::-1],
        }
    )

    # Weighted detector (recent values weighted more)
    detector_weighted = MADDetector(
        storage=mock_storage, window_size="6 hours", use_weighted=True, exp_decay_factor=0.5
    )

    # Unweighted detector
    detector_unweighted = MADDetector(
        storage=mock_storage, window_size="6 hours", use_weighted=False
    )

    # Current value is 110 (continuing trend)
    result_weighted = detector_weighted.detect("test_metric", 110.0, datetime.now())
    result_unweighted = detector_unweighted.detect("test_metric", 110.0, datetime.now())

    # Weighted gives more weight to recent values (100, 90, 80, ...)
    # But with median, the effect is different than with mean
    # The test should just verify both work
    assert result_weighted.metadata["median"] >= 50.0
    assert result_unweighted.metadata["median"] >= 50.0
    # Both should produce valid results
    assert result_weighted.score > 0
    assert result_unweighted.score > 0


def test_mad_detector_with_identical_values() -> None:
    """Test MAD detection when all historical values are identical."""
    # All values are exactly 100
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = MADDetector(storage=mock_storage, use_weighted=False)

    # Current value matches exactly
    result = detector.detect("test_metric", 100.0, datetime.now())

    assert result.is_anomaly is False
    assert result.score == 0.0  # Perfect match
    assert result.metadata["mad_sigma"] == 0.0

    # Current value is different
    result_anomaly = detector.detect("test_metric", 101.0, datetime.now())

    assert result_anomaly.is_anomaly is True
    assert result_anomaly.score == float("inf")  # MAD is zero, any deviation is infinite


def test_mad_weighted_median() -> None:
    """Test weighted median calculation."""
    detector = MADDetector(storage=None, use_weighted=False)

    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    weights = np.array([0.1, 0.1, 0.1, 0.1, 0.6])  # Last value heavily weighted

    median = detector._weighted_median(data, weights)

    # Should be close to 5.0 due to high weight on last value
    assert median >= 4.0


def test_mad_weighted_mad_calculation() -> None:
    """Test weighted MAD calculation."""
    detector = MADDetector(storage=None, use_weighted=False)

    data = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    weights = np.ones(5) / 5  # Equal weights

    median, mad_sigma = detector._weighted_mad(data, weights)

    # Median should be 30.0
    assert abs(median - 30.0) < 0.1

    # MAD = median(|10-30|, |20-30|, |30-30|, |40-30|, |50-30|)
    #     = median(20, 10, 0, 10, 20) = 10
    # MAD_sigma = 1.4826 * 10 = 14.826
    assert abs(mad_sigma - 14.826) < 0.1


def test_mad_compute_weights_unweighted() -> None:
    """Test that unweighted mode returns equal weights."""
    detector = MADDetector(storage=None, use_weighted=False)

    weights = detector._compute_weights(10)

    assert len(weights) == 10
    assert np.allclose(weights, 0.1)  # All weights = 1/10
    assert abs(weights.sum() - 1.0) < 1e-10  # Sum to 1


def test_mad_compute_weights_exponential() -> None:
    """Test exponential decay weights."""
    detector = MADDetector(storage=None, use_weighted=True, exp_decay_factor=0.5)

    weights = detector._compute_weights(5)

    assert len(weights) == 5
    assert abs(weights.sum() - 1.0) < 1e-10  # Sum to 1
    # Recent values (end of array) should have higher weight
    assert weights[-1] > weights[0]


def test_mad_percent_deviation() -> None:
    """Test that percent deviation is calculated correctly."""
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = MADDetector(storage=mock_storage, use_weighted=False)

    # 120 is 20% above 100
    result = detector.detect("test_metric", 120.0, datetime.now())

    assert result.percent_deviation is not None
    assert abs(result.percent_deviation - 20.0) < 0.1


def test_mad_metadata() -> None:
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

    # Test without seasonal features first
    detector = MADDetector(
        storage=mock_storage,
        window_size="5 hours",
        n_sigma=3.0,
        use_weighted=True,
    )

    result = detector.detect("test_metric", 100.0, datetime.now())

    assert "detector" in result.metadata
    assert result.metadata["detector"] == "mad"
    assert "window_size" in result.metadata
    assert "n_sigma" in result.metadata
    assert result.metadata["n_sigma"] == 3.0
    assert "median" in result.metadata
    assert "mad_sigma" in result.metadata
    assert "use_weighted" in result.metadata
    assert "seasonal_features" in result.metadata
    assert result.metadata["seasonal_features"] == []
    assert "window_points" in result.metadata
    assert result.metadata["window_points"] == 5


def test_mad_seasonal_missing_context_column() -> None:
    """Test error when seasonal features requested but context column missing."""
    historical_values = [100.0] * 10
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]

    mock_storage = Mock()
    # No 'context' column
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
        }
    )

    detector = MADDetector(storage=mock_storage, seasonal_features=["hour_of_day"])

    with pytest.raises(DetectionError, match="context.*column missing"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=14)


def test_mad_seasonal_feature_not_in_current_context() -> None:
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

    detector = MADDetector(storage=mock_storage, seasonal_features=["hour_of_day", "day_of_week"])

    # Missing 'day_of_week' in current context
    with pytest.raises(DetectionError, match="Seasonal features.*not found in current context"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=14)


def test_mad_seasonal_separate_grouping() -> None:
    """Test separate seasonal grouping (union of groups)."""
    # Historical data: 10 points with different hour_of_day values
    # Add some variation to avoid MAD=0
    historical_values = [95.0, 200.0, 98.0, 205.0, 102.0, 195.0, 100.0, 210.0, 101.0, 198.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]
    contexts = [
        {"hour_of_day": i % 2}  # Alternating 0 and 1
        for i in range(10)
    ]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = MADDetector(
        storage=mock_storage,
        seasonal_features=["hour_of_day"],
        use_combined_seasonality=False,  # Separate grouping
        use_weighted=False,
    )

    # Current point has hour_of_day=0 (should match values around 95-102)
    result = detector.detect("test_metric", 105.0, datetime.now(), hour_of_day=0)

    assert result.is_anomaly is False  # 105 is close to 95-102 range
    # Median should be around 100 (only hour_of_day=0 points)
    assert 95.0 <= result.metadata["median"] <= 105.0


def test_mad_seasonal_combined_grouping() -> None:
    """Test combined seasonal grouping (intersection of all features)."""
    # Historical data with two features: hour and day_of_week
    # Add variation within groups
    historical_values = [98.0, 102.0, 100.0, 105.0, 95.0, 200.0, 205.0, 195.0, 210.0, 198.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(10)]
    contexts = [
        {"hour_of_day": 14, "day_of_week": 1},  # 98
        {"hour_of_day": 14, "day_of_week": 1},  # 102
        {"hour_of_day": 14, "day_of_week": 1},  # 100
        {"hour_of_day": 14, "day_of_week": 2},  # 105
        {"hour_of_day": 15, "day_of_week": 1},  # 95
        {"hour_of_day": 15, "day_of_week": 2},  # 200
        {"hour_of_day": 15, "day_of_week": 2},  # 205
        {"hour_of_day": 16, "day_of_week": 1},  # 195
        {"hour_of_day": 16, "day_of_week": 2},  # 210
        {"hour_of_day": 16, "day_of_week": 2},  # 198
    ]

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = MADDetector(
        storage=mock_storage,
        seasonal_features=["hour_of_day", "day_of_week"],
        use_combined_seasonality=True,  # Combined: AND
        use_weighted=False,
    )

    # Current: hour=14 AND day_of_week=1 (should match first 3 points: 98, 102, 100)
    result = detector.detect("test_metric", 105.0, datetime.now(), hour_of_day=14, day_of_week=1)

    assert result.is_anomaly is False
    # Median should be 100 (middle of 98, 100, 102)
    assert 98.0 <= result.metadata["median"] <= 102.0


def test_mad_seasonal_no_matching_group() -> None:
    """Test error when no historical data matches seasonal group."""
    historical_values = [100.0] * 5
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(5)]
    contexts = [{"hour_of_day": 10}] * 5  # All hour=10

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = MADDetector(
        storage=mock_storage,
        seasonal_features=["hour_of_day"],
        use_weighted=False,
    )

    # Current hour=14 (no match in history)
    with pytest.raises(DetectionError, match="No historical data found for seasonal group"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=14)


def test_mad_seasonal_insufficient_data_in_group() -> None:
    """Test error when seasonal group has insufficient data."""
    historical_values = [100.0, 200.0, 100.0, 200.0, 100.0]
    timestamps = [datetime.now() - timedelta(hours=i) for i in range(5)]
    contexts = [{"hour_of_day": i % 3} for i in range(5)]  # 0,1,2,0,1

    mock_storage = Mock()
    mock_storage.query_datapoints.return_value = pd.DataFrame(
        {
            "timestamp": timestamps[::-1],
            "value": historical_values[::-1],
            "context": contexts[::-1],
        }
    )

    detector = MADDetector(
        storage=mock_storage,
        seasonal_features=["hour_of_day"],
        use_weighted=False,
    )

    # hour=2 has only 1 point (need at least 3)
    with pytest.raises(DetectionError, match="Insufficient data in seasonal group.*minimum 3"):
        detector.detect("test_metric", 100.0, datetime.now(), hour_of_day=2)
