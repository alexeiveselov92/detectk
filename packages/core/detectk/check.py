"""Main orchestrator for metric monitoring.

This module provides the MetricCheck class that orchestrates the complete
pipeline: collect → detect → alert.
"""

import logging
from datetime import datetime
from typing import Any

from detectk.config import ConfigLoader, MetricConfig
from detectk.models import DataPoint, DetectionResult, CheckResult, AlertConditions
from detectk.base import BaseCollector, BaseDetector, BaseAlerter, BaseStorage
from detectk.registry import CollectorRegistry, DetectorRegistry, AlerterRegistry, StorageRegistry
from detectk.exceptions import (
    DetectKError,
    ConfigurationError,
    CollectionError,
    DetectionError,
    StorageError,
    AlertError,
)

logger = logging.getLogger(__name__)


class MetricCheck:
    """Main orchestrator for metric monitoring pipeline.

    This class coordinates the complete workflow:
    1. Load configuration
    2. Collect current metric value
    3. Optionally save to storage
    4. Run anomaly detection
    5. Decide if alert should be sent
    6. Send alert if conditions are met

    The class is designed to be orchestrator-agnostic - it can be called
    from any scheduler (Prefect, Airflow, APScheduler, or simple cron).

    Example:
        >>> from detectk.check import MetricCheck
        >>> from datetime import datetime
        >>>
        >>> # Run metric check
        >>> checker = MetricCheck()
        >>> result = checker.execute("configs/sessions_10min.yaml")
        >>>
        >>> if result.alert_sent:
        ...     print(f"Alert sent: {result.alert_reason}")
        >>>
        >>> # Run with specific execution time (for backtesting)
        >>> result = checker.execute(
        ...     "configs/sessions_10min.yaml",
        ...     execution_time=datetime(2024, 1, 15, 10, 0, 0)
        ... )
    """

    def __init__(self, config_loader: ConfigLoader | None = None) -> None:
        """Initialize MetricCheck orchestrator.

        Args:
            config_loader: Optional custom ConfigLoader instance.
                          If not provided, creates default loader.
        """
        self.config_loader = config_loader or ConfigLoader()

    def execute(
        self,
        config_path: str,
        execution_time: datetime | None = None,
    ) -> CheckResult:
        """Execute complete metric monitoring pipeline.

        This is the main entry point that runs the full pipeline:
        collect → detect → alert.

        Args:
            config_path: Path to metric configuration YAML file
            execution_time: Optional execution time (default: now()).
                          Used for backtesting and scheduled runs.

        Returns:
            CheckResult containing pipeline execution results

        Raises:
            ConfigurationError: If configuration is invalid
            DetectKError: For other pipeline errors (wrapped in CheckResult.errors)

        Example:
            >>> checker = MetricCheck()
            >>> result = checker.execute("configs/sessions.yaml")
            >>> print(f"Anomaly: {result.detection.is_anomaly}")
            >>> print(f"Alert sent: {result.alert_sent}")
        """
        execution_time = execution_time or datetime.now()
        errors: list[str] = []

        try:
            # Step 1: Load and validate configuration
            logger.info(f"Loading configuration from {config_path}")
            config = self._load_config(config_path, execution_time)
            metric_name = config.name

            # Step 2: Collect current metric value
            logger.info(f"Collecting data for metric: {metric_name}")
            datapoint = self._collect_data(config, execution_time)

            # Step 3: Save to storage (if enabled)
            if config.storage.enabled:
                logger.info(f"Saving datapoint to storage for metric: {metric_name}")
                self._save_to_storage(config, metric_name, datapoint, errors)

            # Step 4: Run anomaly detection
            logger.info(f"Running detection for metric: {metric_name}")
            detection = self._run_detection(config, metric_name, datapoint, errors)

            # Step 5: Decide if alert should be sent
            alert_sent = False
            alert_reason = None

            if detection.is_anomaly:
                logger.info(f"Anomaly detected for metric: {metric_name}")
                alert_sent, alert_reason = self._send_alert(config, detection, errors)

            # Step 6: Build final result
            result = CheckResult(
                metric_name=metric_name,
                datapoint=datapoint,
                detection=detection,
                alert_sent=alert_sent,
                alert_reason=alert_reason,
                errors=errors,
            )

            if errors:
                logger.warning(
                    f"Metric check completed with errors: {metric_name}. "
                    f"Errors: {errors}"
                )
            else:
                logger.info(f"Metric check completed successfully: {metric_name}")

            return result

        except ConfigurationError:
            # Configuration errors should be raised immediately
            raise
        except Exception as e:
            # Unexpected errors - log and return error result
            error_msg = f"Unexpected error during metric check: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

            # Return error result with minimal information
            return CheckResult(
                metric_name=config_path,  # Use config path as fallback
                datapoint=DataPoint(timestamp=execution_time, value=0.0),
                detection=DetectionResult(
                    metric_name=config_path,
                    timestamp=execution_time,
                    value=0.0,
                    is_anomaly=False,
                    score=0.0,
                ),
                alert_sent=False,
                errors=errors,
            )

    def _load_config(
        self,
        config_path: str,
        execution_time: datetime,
    ) -> MetricConfig:
        """Load and validate configuration.

        Args:
            config_path: Path to configuration file
            execution_time: Execution time for template rendering

        Returns:
            Validated MetricConfig

        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            return self.config_loader.load_file(
                config_path,
                template_context={"execution_time": execution_time},
            )
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration: {e}",
                config_path=config_path,
            )

    def _collect_data(
        self,
        config: MetricConfig,
        execution_time: datetime,
    ) -> DataPoint:
        """Collect current metric value.

        Args:
            config: Metric configuration
            execution_time: Execution time

        Returns:
            DataPoint with collected value

        Raises:
            CollectionError: If data collection fails
        """
        try:
            # Get collector class from registry
            collector_class = CollectorRegistry.get(config.collector.type)

            # Create collector instance
            collector = collector_class(config.collector.params)

            # Collect data
            datapoint = collector.collect(at_time=execution_time)

            # Close collector resources
            if hasattr(collector, "close"):
                collector.close()

            return datapoint

        except Exception as e:
            raise CollectionError(
                f"Failed to collect data: {e}",
                source=config.collector.type,
            )

    def _save_to_storage(
        self,
        config: MetricConfig,
        metric_name: str,
        datapoint: DataPoint,
        errors: list[str],
    ) -> None:
        """Save datapoint to storage.

        This method does not raise exceptions - errors are added to the errors list.

        Args:
            config: Metric configuration
            metric_name: Metric name
            datapoint: DataPoint to save
            errors: List to append errors to
        """
        try:
            if not config.storage.type:
                # Storage enabled but type not specified - use same as collector
                storage_type = config.collector.type
            else:
                storage_type = config.storage.type

            # Get storage class from registry
            storage_class = StorageRegistry.get(storage_type)

            # Create storage instance
            storage = storage_class(config.storage.params)

            # Save datapoint
            storage.save(metric_name, datapoint)

            logger.debug(f"Saved datapoint to storage: {metric_name}")

        except Exception as e:
            error_msg = f"Failed to save to storage: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    def _run_detection(
        self,
        config: MetricConfig,
        metric_name: str,
        datapoint: DataPoint,
        errors: list[str],
    ) -> DetectionResult:
        """Run anomaly detection.

        Args:
            config: Metric configuration
            metric_name: Metric name
            datapoint: Current datapoint
            errors: List to append errors to

        Returns:
            DetectionResult (with is_anomaly=False on error)
        """
        try:
            # Get detector class from registry
            detector_class = DetectorRegistry.get(config.detector.type)

            # Get or create storage for detector
            if config.storage.enabled:
                if not config.storage.type:
                    storage_type = config.collector.type
                else:
                    storage_type = config.storage.type

                storage_class = StorageRegistry.get(storage_type)
                storage = storage_class(config.storage.params)
            else:
                # No storage - detector must work without historical data
                storage = None  # type: ignore

            # Create detector instance with storage
            detector = detector_class(storage=storage, **config.detector.params)

            # Run detection
            detection = detector.detect(
                metric_name=metric_name,
                value=datapoint.value,
                timestamp=datapoint.timestamp,
            )

            return detection

        except Exception as e:
            error_msg = f"Failed to run detection: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

            # Return non-anomaly result on error
            return DetectionResult(
                metric_name=metric_name,
                timestamp=datapoint.timestamp,
                value=datapoint.value,
                is_anomaly=False,
                score=0.0,
                metadata={"error": str(e)},
            )

    def _send_alert(
        self,
        config: MetricConfig,
        detection: DetectionResult,
        errors: list[str],
    ) -> tuple[bool, str | None]:
        """Send alert if conditions are met.

        Args:
            config: Metric configuration
            detection: Detection result
            errors: List to append errors to

        Returns:
            Tuple of (alert_sent, alert_reason)
        """
        try:
            # Parse alert conditions
            alert_conditions = AlertConditions(**config.alerter.conditions)

            # For now, send alert immediately if anomaly detected
            # TODO: Implement AlertAnalyzer for sophisticated logic
            # (consecutive anomalies, direction filtering, cooldown)
            should_alert = detection.is_anomaly

            if not should_alert:
                return False, None

            # Get alerter class from registry
            alerter_class = AlerterRegistry.get(config.alerter.type)

            # Create alerter instance
            alerter = alerter_class(config.alerter.params)

            # Send alert
            success = alerter.send(detection)

            if success:
                reason = f"Anomaly detected: score={detection.score:.2f}"
                logger.info(f"Alert sent successfully: {detection.metric_name}")
                return True, reason
            else:
                error_msg = "Alert sending failed (returned False)"
                logger.warning(error_msg)
                errors.append(error_msg)
                return False, None

        except Exception as e:
            error_msg = f"Failed to send alert: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
            return False, None
