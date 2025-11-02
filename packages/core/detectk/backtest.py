"""Backtesting functionality for DetectK.

Allows testing anomaly detection algorithms on historical data before
deploying to production.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from dateutil import parser as date_parser

from detectk.check import MetricCheck
from detectk.config.loader import ConfigLoader
from detectk.config.models import MetricConfig
from detectk.exceptions import ConfigurationError
from detectk.models import CheckResult

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from backtesting run.

    Attributes:
        metric_name: Name of the metric tested
        total_checks: Total number of detection runs
        anomalies_detected: Number of anomalies found
        alerts_sent: Number of alerts actually sent (after cooldown)
        start_time: When backtesting started
        end_time: When backtesting finished
        duration_seconds: Total execution time
        results: List of all CheckResult objects
        summary: Summary statistics as DataFrame
    """

    metric_name: str
    total_checks: int
    anomalies_detected: int
    alerts_sent: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    results: list[CheckResult]
    summary: pd.DataFrame | None = None


class BacktestRunner:
    """Runs backtesting for metric configurations.

    Philosophy: Reuse production code path!
    - Same MetricCheck.execute() method
    - Just iterate through time steps
    - No separate backtest-specific logic
    """

    def __init__(self) -> None:
        """Initialize backtesting runner."""
        self.checker = MetricCheck()

    def run(self, config_path: str | Path) -> BacktestResult:
        """Run backtesting for a metric configuration.

        Args:
            config_path: Path to metric configuration YAML file

        Returns:
            BacktestResult with aggregated results

        Raises:
            ConfigurationError: If backtest config is invalid
        """
        # Load configuration
        loader = ConfigLoader()
        config = loader.load_file(str(config_path))

        # Validate backtest configuration
        if not config.backtest.enabled:
            raise ConfigurationError(
                "Backtesting not enabled in configuration. Set backtest.enabled: true",
                config_path="backtest.enabled",
            )

        self._validate_backtest_config(config)

        # Parse dates
        data_load_start = self._parse_datetime(config.backtest.data_load_start)
        detection_start = self._parse_datetime(config.backtest.detection_start)
        detection_end = self._parse_datetime(config.backtest.detection_end)
        step_interval = self._parse_interval(config.backtest.step_interval)

        logger.info(f"Starting backtest for: {config.name}")
        logger.info(f"  Data load start: {data_load_start}")
        logger.info(f"  Detection period: {detection_start} to {detection_end}")
        logger.info(f"  Step interval: {step_interval}")

        # Run backtest
        start_time = datetime.now()
        results = self._run_backtest_loop(
            config_path=str(config_path),
            detection_start=detection_start,
            detection_end=detection_end,
            step_interval=step_interval,
        )
        end_time = datetime.now()

        # Aggregate results
        total_checks = len(results)
        anomalies_detected = sum(1 for r in results if r.detection and r.detection.is_anomaly)
        alerts_sent = sum(1 for r in results if r.alert_sent)

        duration = (end_time - start_time).total_seconds()

        logger.info(f"Backtest completed in {duration:.2f}s")
        logger.info(f"  Total checks: {total_checks}")
        logger.info(f"  Anomalies detected: {anomalies_detected}")
        logger.info(f"  Alerts sent: {alerts_sent}")

        # Create summary DataFrame
        summary = self._create_summary(results)

        return BacktestResult(
            metric_name=config.name,
            total_checks=total_checks,
            anomalies_detected=anomalies_detected,
            alerts_sent=alerts_sent,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            results=results,
            summary=summary,
        )

    def _validate_backtest_config(self, config: MetricConfig) -> None:
        """Validate backtest configuration.

        Args:
            config: Metric configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        backtest = config.backtest

        if not backtest.data_load_start:
            raise ConfigurationError(
                "backtest.data_load_start is required when backtesting is enabled",
                config_path="backtest.data_load_start",
            )

        if not backtest.detection_start:
            raise ConfigurationError(
                "backtest.detection_start is required when backtesting is enabled",
                config_path="backtest.detection_start",
            )

        if not backtest.detection_end:
            raise ConfigurationError(
                "backtest.detection_end is required when backtesting is enabled",
                config_path="backtest.detection_end",
            )

        if not backtest.step_interval:
            raise ConfigurationError(
                "backtest.step_interval is required when backtesting is enabled",
                config_path="backtest.step_interval",
            )

        # Validate date order
        data_load_start = self._parse_datetime(backtest.data_load_start)
        detection_start = self._parse_datetime(backtest.detection_start)
        detection_end = self._parse_datetime(backtest.detection_end)

        if data_load_start >= detection_start:
            raise ConfigurationError(
                f"data_load_start ({data_load_start}) must be before detection_start ({detection_start})",
                config_path="backtest",
            )

        if detection_start >= detection_end:
            raise ConfigurationError(
                f"detection_start ({detection_start}) must be before detection_end ({detection_end})",
                config_path="backtest",
            )

    def _parse_datetime(self, dt_str: str | None) -> datetime:
        """Parse datetime string.

        Args:
            dt_str: Datetime string (e.g., "2024-01-01", "2024-01-01 14:30:00")

        Returns:
            Parsed datetime

        Raises:
            ConfigurationError: If parsing fails
        """
        if not dt_str:
            raise ConfigurationError("Datetime string cannot be empty")

        try:
            return date_parser.parse(dt_str)
        except Exception as e:
            raise ConfigurationError(
                f"Invalid datetime format: {dt_str}. Error: {e}",
                config_path="backtest",
            ) from e

    def _parse_interval(self, interval_str: str | None) -> timedelta:
        """Parse interval string to timedelta.

        Args:
            interval_str: Interval string (e.g., "10 minutes", "1 hour", "1 day")

        Returns:
            timedelta object

        Raises:
            ConfigurationError: If parsing fails
        """
        if not interval_str:
            raise ConfigurationError("Interval string cannot be empty")

        interval_str = interval_str.strip().lower()

        # Parse simple formats: "N unit" (e.g., "10 minutes", "1 hour")
        parts = interval_str.split()
        if len(parts) != 2:
            raise ConfigurationError(
                f"Invalid interval format: {interval_str}. "
                "Expected format: '<number> <unit>' (e.g., '10 minutes', '1 hour')"
            )

        try:
            value = int(parts[0])
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid interval value: {parts[0]}. Must be an integer.",
                config_path="backtest.step_interval",
            ) from e

        unit = parts[1].rstrip("s")  # Remove trailing 's' (minutes/minute)

        unit_map = {
            "second": timedelta(seconds=value),
            "minute": timedelta(minutes=value),
            "hour": timedelta(hours=value),
            "day": timedelta(days=value),
            "week": timedelta(weeks=value),
        }

        if unit not in unit_map:
            raise ConfigurationError(
                f"Invalid interval unit: {parts[1]}. "
                f"Supported units: {', '.join(unit_map.keys())} (with optional 's')",
                config_path="backtest.step_interval",
            )

        return unit_map[unit]

    def _run_backtest_loop(
        self,
        config_path: str,
        detection_start: datetime,
        detection_end: datetime,
        step_interval: timedelta,
    ) -> list[CheckResult]:
        """Run backtest loop through time steps.

        Args:
            config_path: Path to configuration file
            detection_start: Start time for detection
            detection_end: End time for detection
            step_interval: Time step between checks

        Returns:
            List of CheckResult objects
        """
        results = []
        current_time = detection_start

        # Calculate total steps for progress tracking
        total_steps = int((detection_end - detection_start) / step_interval)
        step_count = 0

        while current_time <= detection_end:
            step_count += 1

            # Log progress every 10% or every 100 steps
            if step_count % max(1, total_steps // 10) == 0 or step_count % 100 == 0:
                progress = (step_count / total_steps) * 100
                logger.info(f"  Progress: {step_count}/{total_steps} ({progress:.1f}%)")

            # Execute check at this time point
            # MetricCheck.execute() handles everything: collect → detect → alert
            result = self.checker.execute(
                config_path=config_path,
                execution_time=current_time,
            )

            results.append(result)

            # Move to next time step
            current_time += step_interval

        return results

    def _create_summary(self, results: list[CheckResult]) -> pd.DataFrame:
        """Create summary DataFrame from results.

        Args:
            results: List of CheckResult objects

        Returns:
            DataFrame with summary statistics
        """
        if not results:
            return pd.DataFrame()

        records = []
        for result in results:
            if result.detection:
                records.append(
                    {
                        "timestamp": result.timestamp,
                        "value": result.value,
                        "is_anomaly": result.detection.is_anomaly,
                        "score": result.detection.score,
                        "lower_bound": result.detection.lower_bound,
                        "upper_bound": result.detection.upper_bound,
                        "direction": result.detection.direction,
                        "percent_deviation": result.detection.percent_deviation,
                        "alert_sent": result.alert_sent,
                    }
                )

        return pd.DataFrame(records)

    def save_results(self, result: BacktestResult, output_path: str | Path) -> None:
        """Save backtest results to CSV file.

        Args:
            result: BacktestResult object
            output_path: Path to save CSV file
        """
        if result.summary is None or result.summary.empty:
            logger.warning("No results to save")
            return

        output_path = Path(output_path)
        result.summary.to_csv(output_path, index=False)
        logger.info(f"Results saved to: {output_path}")
