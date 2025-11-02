"""MAD (Median Absolute Deviation) anomaly detector.

Robust statistical detector that uses median and MAD instead of mean and standard
deviation. More resistant to outliers compared to Z-score methods.

The MAD is defined as:
    MAD = median(|X_i - median(X)|)

For comparison with standard deviation (assuming normal distribution):
    MAD_sigma = 1.4826 * MAD

This makes MAD comparable to standard deviation for normally distributed data,
while remaining robust to outliers.
"""

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from detectk.base.detector import BaseDetector
from detectk.base.storage import BaseStorage
from detectk.exceptions import DetectionError
from detectk.models import DetectionResult
from detectk.registry.detector import DetectorRegistry


@DetectorRegistry.register("mad")
class MADDetector(BaseDetector):
    """Median Absolute Deviation (MAD) anomaly detector.

    Uses median and MAD for robust anomaly detection. More resistant to outliers
    than mean/std-based methods.

    Key features:
    - Weighted statistics (exponential decay) - recent data weighted more
    - Seasonal grouping support (hour_of_day, day_of_week, custom features)
    - Combined seasonality (multiple features at once)
    - Robust to outliers

    Configuration parameters:
        window_size: Historical window for statistics calculation
                    Examples: "30 days", "7 days", "24 hours"
                    Or integer for number of points
        n_sigma: Number of MAD sigmas for anomaly threshold (default: 3.0)
                Higher values = fewer anomalies detected
        use_weighted: Use exponential decay weights for recent data (default: True)
        exp_decay_factor: Exponential decay factor for weights (default: 0.1)
                         Higher = more weight to recent data
        seasonal_features: List of seasonal feature names to group by (default: [])
                          Features must be present in datapoint metadata
                          Examples: ["hour_of_day", "day_of_week"]
        use_combined_seasonality: Group by all features simultaneously (default: False)
                                 If True: groups by (hour, dow) together
                                 If False: separate statistics per feature

    Example configuration:
        detector:
          type: "mad"
          params:
            window_size: "30 days"
            n_sigma: 3.0
            use_weighted: true
            exp_decay_factor: 0.1
            seasonal_features: ["hour_of_day", "day_of_week"]
            use_combined_seasonality: false

    Algorithm:
        1. Load historical window from storage
        2. Extract seasonal features from metadata
        3. Group by seasonal features (if specified)
        4. Calculate weighted median and MAD for each group
        5. Check if current value is > median + n_sigma * MAD_sigma
        6. Return detection result with bounds and score
    """

    def __init__(
        self,
        storage: BaseStorage | None,
        window_size: str | int = "30 days",
        n_sigma: float = 3.0,
        use_weighted: bool = True,
        exp_decay_factor: float = 0.1,
        seasonal_features: list[str] | None = None,
        use_combined_seasonality: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize MAD detector.

        Args:
            storage: Storage backend for loading historical data
            window_size: Historical window ("30 days" or integer points)
            n_sigma: Number of MAD sigmas for anomaly threshold
            use_weighted: Use exponential decay weights
            exp_decay_factor: Exponential decay factor (higher = more recent weight)
            seasonal_features: List of feature names to group by
            use_combined_seasonality: Group by all features together
            **kwargs: Additional parameters (ignored)
        """
        super().__init__(storage)
        self.window_size = window_size
        self.n_sigma = n_sigma
        self.use_weighted = use_weighted
        self.exp_decay_factor = exp_decay_factor
        self.seasonal_features = seasonal_features or []
        self.use_combined_seasonality = use_combined_seasonality

        # Validate configuration
        self.validate_config(
            {
                "window_size": window_size,
                "n_sigma": n_sigma,
                "use_weighted": use_weighted,
                "exp_decay_factor": exp_decay_factor,
                "seasonal_features": self.seasonal_features,
                "use_combined_seasonality": use_combined_seasonality,
            }
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate detector configuration.

        Args:
            config: Configuration dictionary

        Raises:
            DetectionError: If configuration is invalid
        """
        n_sigma = config.get("n_sigma", self.n_sigma if hasattr(self, "n_sigma") else 3.0)
        if n_sigma <= 0:
            raise DetectionError(f"n_sigma must be positive, got {n_sigma}")

        exp_decay_factor = config.get(
            "exp_decay_factor",
            self.exp_decay_factor if hasattr(self, "exp_decay_factor") else 0.1,
        )
        if exp_decay_factor <= 0:
            raise DetectionError(f"exp_decay_factor must be positive, got {exp_decay_factor}")

        seasonal_features = config.get(
            "seasonal_features",
            self.seasonal_features if hasattr(self, "seasonal_features") else [],
        )
        if not isinstance(seasonal_features, list):
            raise DetectionError(
                f"seasonal_features must be a list, got {type(seasonal_features).__name__}"
            )

    def detect(
        self,
        metric_name: str,
        value: float | None,
        timestamp: datetime,
        **context: Any,
    ) -> DetectionResult:
        """Detect anomalies using MAD algorithm.

        Args:
            metric_name: Name of the metric
            value: Current metric value (None if missing data)
            timestamp: Timestamp of measurement
            **context: Additional context (may contain seasonal features, is_missing flag)

        Returns:
            DetectionResult with anomaly status, bounds, score

        Raises:
            DetectionError: If detection fails or insufficient data

        Note:
            If value is None or is_missing=True, returns non-anomalous result.
            Use MissingDataDetector for explicit missing data detection.
        """
        # Handle missing data - skip detection
        if value is None or context.get("is_missing", False):
            return DetectionResult(
                metric_name=metric_name,
                timestamp=timestamp,
                value=value,
                is_anomaly=False,
                score=0.0,
                metadata={
                    "detector": "mad",
                    "skipped": "missing_data",
                    "reason": "Cannot perform MAD detection on missing data",
                },
            )

        if self.storage is None:
            raise DetectionError("MADDetector requires storage for historical data")

        # Load historical window
        try:
            df = self.storage.query_datapoints(
                metric_name=metric_name,
                window=self.window_size,
                end_time=timestamp,
            )
        except Exception as e:
            raise DetectionError(f"Failed to load historical data: {e}") from e

        if df.empty:
            raise DetectionError(
                f"No historical data found for metric '{metric_name}' "
                f"within window {self.window_size}"
            )

        # Need at least 3 points for meaningful MAD
        if len(df) < 3:
            raise DetectionError(
                f"Insufficient data for MAD detection: {len(df)} points "
                f"(minimum 3 required)"
            )

        # Calculate statistics
        if self.seasonal_features:
            # Seasonal detection with grouping
            median, mad_sigma = self._calculate_seasonal_stats(df, context)
        else:
            # Simple detection without seasonality
            values = df["value"].values
            weights = self._compute_weights(len(values))
            median, mad_sigma = self._weighted_mad(values, weights)

        # Calculate bounds
        lower_bound = median - self.n_sigma * mad_sigma
        upper_bound = median + self.n_sigma * mad_sigma

        # Check for anomaly
        is_anomaly = value < lower_bound or value > upper_bound

        # Calculate score (how many sigmas away from median)
        if mad_sigma > 0:
            score = abs(value - median) / mad_sigma
        else:
            # MAD is zero (all values identical) - perfect match or extreme outlier
            score = 0.0 if value == median else float("inf")

        # Determine direction
        direction = None
        if is_anomaly:
            direction = "up" if value > upper_bound else "down"

        # Calculate percent deviation
        percent_deviation = None
        if median != 0:
            percent_deviation = ((value - median) / abs(median)) * 100

        return DetectionResult(
            metric_name=metric_name,
            timestamp=timestamp,
            value=value,
            is_anomaly=is_anomaly,
            score=score,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            direction=direction,
            percent_deviation=percent_deviation,
            metadata={
                "detector": "mad",
                "window_size": str(self.window_size),
                "n_sigma": self.n_sigma,
                "median": median,
                "mad_sigma": mad_sigma,
                "use_weighted": self.use_weighted,
                "seasonal_features": self.seasonal_features,
                "window_points": len(df),
            },
        )

    def _compute_weights(self, size: int) -> np.ndarray:
        """Calculate exponential decay weights for time series.

        Recent data points get higher weights. Weights are normalized to sum to 1.

        Args:
            size: Number of points in window

        Returns:
            Normalized weight array
        """
        if not self.use_weighted:
            return np.ones(size) / size

        # Exponential decay: recent points (end of array) get higher weight
        # weights[i] = exp(-decay * distance_from_end)
        weights = np.exp(-self.exp_decay_factor * np.arange(size)[::-1])

        # Normalize to sum to 1
        return weights / weights.sum()

    def _weighted_median(self, data: np.ndarray, weights: np.ndarray) -> float:
        """Calculate weighted median.

        Args:
            data: Data values
            weights: Weights for each value (must sum to 1)

        Returns:
            Weighted median value
        """
        # Sort data and weights together
        sorted_idx = np.argsort(data)
        sorted_data = data[sorted_idx]
        sorted_weights = weights[sorted_idx]

        # Cumulative sum of weights
        cumsum = np.cumsum(sorted_weights)

        # Find value where cumulative weight crosses 0.5
        median_idx = np.searchsorted(cumsum, 0.5)

        return float(sorted_data[median_idx])

    def _weighted_mad(self, data: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
        """Calculate weighted median and MAD (Median Absolute Deviation).

        The constant 1.4826 makes MAD comparable to standard deviation
        for normally distributed data.

        Args:
            data: Data values
            weights: Weights for each value

        Returns:
            Tuple of (median, mad_sigma)
        """
        # Calculate weighted median
        median = self._weighted_median(data, weights)

        # Calculate absolute deviations
        abs_dev = np.abs(data - median)

        # MAD is median of absolute deviations
        mad = self._weighted_median(abs_dev, weights)

        # Convert to sigma-equivalent (for normal distribution)
        mad_sigma = 1.4826 * mad

        return median, mad_sigma

    def _calculate_seasonal_stats(
        self, df: pd.DataFrame, context: dict[str, Any]
    ) -> tuple[float, float]:
        """Calculate statistics with seasonal grouping.

        Groups historical data by seasonal features (e.g., hour_of_day, day_of_week)
        and calculates statistics only for matching group.

        Args:
            df: Historical dataframe with 'value' column and 'context' JSON column
            context: Current context with seasonal feature values

        Returns:
            Tuple of (median, mad_sigma) for current seasonal group

        Raises:
            DetectionError: If seasonal features missing or insufficient data in group
        """
        # Parse context column (JSON) to extract seasonal features
        if "context" not in df.columns:
            raise DetectionError(
                f"Seasonal features requested but 'context' column missing in historical data"
            )

        # Extract seasonal features from context column
        seasonal_data = []
        for ctx in df["context"]:
            if ctx is None:
                seasonal_data.append({})
            elif isinstance(ctx, dict):
                seasonal_data.append(ctx)
            else:
                # Try parsing as JSON string
                import json

                try:
                    seasonal_data.append(json.loads(ctx))
                except (json.JSONDecodeError, TypeError):
                    seasonal_data.append({})

        # Build seasonal feature columns
        for feature_name in self.seasonal_features:
            df[feature_name] = [ctx.get(feature_name) for ctx in seasonal_data]

        # Check if current context has required features
        missing_features = [f for f in self.seasonal_features if f not in context]
        if missing_features:
            raise DetectionError(
                f"Seasonal features {missing_features} not found in current context. "
                f"Available: {list(context.keys())}"
            )

        # Filter data by seasonal group
        if self.use_combined_seasonality:
            # Combined: group by ALL features simultaneously
            mask = pd.Series([True] * len(df))
            for feature_name in self.seasonal_features:
                current_value = context[feature_name]
                mask &= df[feature_name] == current_value

            filtered_df = df[mask]
        else:
            # Separate: use UNION of all individual feature groups
            masks = []
            for feature_name in self.seasonal_features:
                current_value = context[feature_name]
                masks.append(df[feature_name] == current_value)

            # Combine masks with OR (union)
            combined_mask = pd.Series([False] * len(df))
            for mask in masks:
                combined_mask |= mask

            filtered_df = df[combined_mask]

        if filtered_df.empty:
            raise DetectionError(
                f"No historical data found for seasonal group: "
                f"{[(f, context[f]) for f in self.seasonal_features]}"
            )

        if len(filtered_df) < 3:
            raise DetectionError(
                f"Insufficient data in seasonal group: {len(filtered_df)} points "
                f"(minimum 3 required)"
            )

        # Calculate statistics for filtered group
        values = filtered_df["value"].values
        weights = self._compute_weights(len(values))
        median, mad_sigma = self._weighted_mad(values, weights)

        return median, mad_sigma
