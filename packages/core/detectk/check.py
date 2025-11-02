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

            # Step 4: Run anomaly detection (possibly multiple detectors)
            logger.info(f"Running detection for metric: {metric_name}")
            detections = self._run_detections(config, metric_name, datapoint, errors)

            # Step 5: Decide if alert should be sent (based on all detectors)
            alert_sent = False
            alert_reason = None

            # Check if any detector found anomaly
            any_anomaly = any(d.is_anomaly for d in detections)

            if any_anomaly:
                logger.info(f"Anomaly detected for metric: {metric_name}")
                # For now, send alert if ANY detector finds anomaly
                # TODO: Make alert strategy configurable (any/all/majority)
                alert_sent, alert_reason = self._send_alert(config, detections, errors)

            # Step 6: Build final result
            # For backward compatibility, use first detection as primary
            # TODO: Update CheckResult model to support multiple detections
            primary_detection = detections[0] if detections else DetectionResult(
                metric_name=metric_name,
                timestamp=datapoint.timestamp,
                value=datapoint.value,
                is_anomaly=False,
                score=0.0,
            )

            result = CheckResult(
                metric_name=metric_name,
                datapoint=datapoint,
                detection=primary_detection,
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
            DataPoint with collected value (latest from time range)

        Raises:
            CollectionError: If data collection fails
        """
        try:
            from datetime import timedelta

            # Get collector class from registry
            collector_class = CollectorRegistry.get(config.collector.type)

            # Create collector instance
            collector = collector_class(config.collector.params)

            # Determine time range for collection
            # For real-time mode: collect data for last interval period
            # Default to 10 minutes if no schedule specified
            if config.schedule and config.schedule.interval:
                # Parse interval string (e.g., "10 minutes")
                interval_str = config.schedule.interval
                # Simple parsing for common cases
                if "minute" in interval_str:
                    minutes = int(interval_str.split()[0])
                    delta = timedelta(minutes=minutes)
                elif "hour" in interval_str:
                    hours = int(interval_str.split()[0])
                    delta = timedelta(hours=hours)
                else:
                    delta = timedelta(minutes=10)  # Default
            else:
                delta = timedelta(minutes=10)  # Default

            period_finish = execution_time
            period_start = execution_time - delta

            # Collect data for time range
            datapoints = collector.collect_bulk(
                period_start=period_start,
                period_finish=period_finish,
            )

            # Close collector resources
            if hasattr(collector, "close"):
                collector.close()

            # Return the latest datapoint (or create one if empty)
            if datapoints:
                return datapoints[-1]  # Latest point
            else:
                # No data collected - return placeholder
                return DataPoint(timestamp=execution_time, value=None, is_missing=True)

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

            # Save datapoint to dtk_datapoints table (as single-item list)
            storage.save_datapoints_bulk(metric_name, [datapoint])

            logger.debug(f"Saved datapoint to storage: {metric_name}")

        except Exception as e:
            error_msg = f"Failed to save to storage: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    def _run_detections(
        self,
        config: MetricConfig,
        metric_name: str,
        datapoint: DataPoint,
        errors: list[str],
    ) -> list[DetectionResult]:
        """Run anomaly detection with all configured detectors.

        Args:
            config: Metric configuration
            metric_name: Metric name
            datapoint: Current datapoint
            errors: List to append errors to

        Returns:
            List of DetectionResult (one per detector)
        """
        detections = []

        # Get list of detectors (handles both single and multiple)
        detector_configs = config.get_detectors()

        # Get storage once (shared by all detectors)
        storage = None
        if config.storage.enabled:
            try:
                if not config.storage.type:
                    storage_type = config.collector.type
                else:
                    storage_type = config.storage.type

                storage_class = StorageRegistry.get(storage_type)
                storage = storage_class(config.storage.params)
            except Exception as e:
                error_msg = f"Failed to create storage for detectors: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                storage = None

        # Run each detector
        for detector_config in detector_configs:
            try:
                # Get detector class from registry
                detector_class = DetectorRegistry.get(detector_config.type)

                # Create detector instance with storage
                detector = detector_class(storage=storage, **detector_config.params)

                # Run detection
                detection = detector.detect(
                    metric_name=metric_name,
                    value=datapoint.value,
                    timestamp=datapoint.timestamp,
                )

                # Add detector_id to metadata for tracking
                # Since DetectionResult is frozen, we need to create a new instance
                updated_metadata = detection.metadata.copy() if detection.metadata else {}
                updated_metadata["detector_id"] = detector_config.id
                updated_metadata["detector_type"] = detector_config.type

                # Create new detection with updated metadata
                detection_with_id = DetectionResult(
                    metric_name=detection.metric_name,
                    timestamp=detection.timestamp,
                    value=detection.value,
                    is_anomaly=detection.is_anomaly,
                    score=detection.score,
                    lower_bound=detection.lower_bound,
                    upper_bound=detection.upper_bound,
                    direction=detection.direction,
                    percent_deviation=detection.percent_deviation,
                    metadata=updated_metadata,
                )

                detections.append(detection_with_id)

                # Save detection result to storage (if enabled)
                if storage and config.storage.params.get("save_detections", False):
                    try:
                        storage.save_detection(
                            metric_name=metric_name,
                            detection=detection_with_id,
                            detector_id=detector_config.id,
                            alert_sent=False,  # Will be updated later if alert sent
                        )
                    except Exception as e:
                        error_msg = f"Failed to save detection for detector {detector_config.id}: {e}"
                        logger.error(error_msg, exc_info=True)
                        errors.append(error_msg)

                logger.debug(
                    f"Detector {detector_config.id} result: "
                    f"anomaly={detection.is_anomaly}, score={detection.score}"
                )

            except Exception as e:
                error_msg = f"Failed to run detector {detector_config.id}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

                # Add error detection result
                detections.append(
                    DetectionResult(
                        metric_name=metric_name,
                        timestamp=datapoint.timestamp,
                        value=datapoint.value,
                        is_anomaly=False,
                        score=0.0,
                        metadata={
                            "detector_id": detector_config.id,
                            "detector_type": detector_config.type,
                            "error": str(e)
                        },
                    )
                )

        # If no detections (all failed), return single error detection
        if not detections:
            detections.append(
                DetectionResult(
                    metric_name=metric_name,
                    timestamp=datapoint.timestamp,
                    value=datapoint.value,
                    is_anomaly=False,
                    score=0.0,
                    metadata={"error": "All detectors failed"},
                )
            )

        return detections

    def _send_alert(
        self,
        config: MetricConfig,
        detections: list[DetectionResult],
        errors: list[str],
    ) -> tuple[bool, str | None]:
        """Send alert if conditions are met.

        Args:
            config: Metric configuration
            detections: List of detection results from all detectors
            errors: List to append errors to

        Returns:
            Tuple of (alert_sent, alert_reason)
        """
        try:
            # Parse alert conditions
            alert_conditions = AlertConditions(**config.alerter.conditions)

            # For now, send alert if ANY detector found anomaly
            # TODO: Make alert strategy configurable (any/all/majority)
            # TODO: Implement AlertAnalyzer for sophisticated logic
            # (consecutive anomalies, direction filtering, cooldown)
            anomalous_detections = [d for d in detections if d.is_anomaly]

            if not anomalous_detections:
                return False, None

            # Get alerter class from registry
            alerter_class = AlerterRegistry.get(config.alerter.type)

            # Create alerter instance
            alerter = alerter_class(config.alerter.params)

            # Send alert for first anomalous detection
            # TODO: Update alerters to handle multiple detections
            primary_detection = anomalous_detections[0]
            success = alerter.send(primary_detection)

            if success:
                # Build reason mentioning all anomalous detectors
                detector_ids = [d.metadata.get("detector_id", "unknown") for d in anomalous_detections]
                if len(detector_ids) == 1:
                    reason = f"Anomaly detected by detector {detector_ids[0]}: score={primary_detection.score:.2f}"
                else:
                    reason = (
                        f"Anomalies detected by {len(detector_ids)} detectors "
                        f"({', '.join(detector_ids)}): primary_score={primary_detection.score:.2f}"
                    )

                logger.info(f"Alert sent successfully: {primary_detection.metric_name}")
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
