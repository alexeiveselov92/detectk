"""Base classes for alert sending and decision making.

Separation of concerns:
- AlertAnalyzer: Makes decision whether to send alert (business logic)
- BaseAlerter: Sends alert message (infrastructure)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from detectk.models import DetectionResult, AlertConditions
from detectk.exceptions import AlertError


class AlertAnalyzer:
    """Analyzes detection results to decide if alert should be sent.

    This class implements alert policy logic:
    - Consecutive anomaly checking
    - Direction filtering
    - Minimum deviation threshold
    - Cooldown management

    Separated from Alerter to keep business logic separate from infrastructure.

    Example:
        >>> analyzer = AlertAnalyzer()
        >>> conditions = AlertConditions(
        ...     consecutive_anomalies=3,
        ...     direction="both",
        ...     cooldown_minutes=60
        ... )
        >>> should_alert, reason = analyzer.should_alert(
        ...     current_result,
        ...     conditions,
        ...     recent_results
        ... )
        >>> if should_alert:
        ...     alerter.send(current_result)
    """

    def __init__(self) -> None:
        """Initialize alert analyzer.

        Can maintain state for cooldown tracking if needed.
        """
        self._last_alert_times: dict[str, datetime] = {}

    def should_alert(
        self,
        result: DetectionResult,
        conditions: AlertConditions,
        recent_results: list[DetectionResult] | None = None,
    ) -> tuple[bool, str]:
        """Determine if alert should be sent based on conditions.

        Args:
            result: Current detection result
            conditions: Alert conditions from config
            recent_results: Recent detection results for consecutive check
                          Should be ordered from oldest to newest
                          If None, only checks current result

        Returns:
            (should_alert, reason) tuple
            - should_alert: Whether to send alert
            - reason: Human-readable explanation of decision

        Example:
            >>> should_alert, reason = analyzer.should_alert(
            ...     result=current,
            ...     conditions=AlertConditions(consecutive_anomalies=3),
            ...     recent_results=[result1, result2, current]
            ... )
            >>> print(reason)
            "3 consecutive upward anomalies detected"
        """
        metric_name = result.metric_name

        # Check if current point is anomaly
        if not result.is_anomaly:
            return False, "Current value is not anomalous"

        # Check minimum deviation threshold
        if conditions.min_deviation_percent is not None:
            if result.percent_deviation is None:
                return False, "Cannot check min deviation: percent_deviation not calculated"

            abs_deviation = abs(result.percent_deviation)
            if abs_deviation < conditions.min_deviation_percent:
                return (
                    False,
                    f"Deviation {abs_deviation:.1f}% below threshold {conditions.min_deviation_percent}%",
                )

        # Check direction filter
        if conditions.direction != "both":
            if result.direction is None:
                return False, "Cannot check direction: direction not determined"

            if conditions.direction == "up" and result.direction != "up":
                return False, f"Anomaly direction is {result.direction}, expected up"

            if conditions.direction == "down" and result.direction != "down":
                return False, f"Anomaly direction is {result.direction}, expected down"

            if conditions.direction == "one":
                # For "one" direction: all consecutive anomalies must be in same direction
                if recent_results and len(recent_results) > 1:
                    directions = [r.direction for r in recent_results if r.is_anomaly]
                    if len(set(directions)) > 1:
                        return False, "Consecutive anomalies in different directions (expected one direction)"

        # Check consecutive anomalies
        if conditions.consecutive_anomalies > 1:
            if recent_results is None:
                return False, "Cannot check consecutive anomalies: recent_results not provided"

            # Count consecutive anomalies at the end of the list
            consecutive_count = 0
            for r in reversed(recent_results):
                if r.is_anomaly:
                    consecutive_count += 1
                else:
                    break

            if consecutive_count < conditions.consecutive_anomalies:
                return (
                    False,
                    f"Only {consecutive_count}/{conditions.consecutive_anomalies} consecutive anomalies",
                )

        # Check cooldown
        if conditions.cooldown_minutes > 0:
            if metric_name in self._last_alert_times:
                last_alert = self._last_alert_times[metric_name]
                time_since_alert = result.timestamp - last_alert
                cooldown_delta = timedelta(minutes=conditions.cooldown_minutes)

                if time_since_alert < cooldown_delta:
                    remaining = cooldown_delta - time_since_alert
                    return False, f"Within cooldown period ({remaining.total_seconds() / 60:.1f} min remaining)"

        # All conditions met - should alert!
        direction_str = result.direction if result.direction else "any"

        if conditions.consecutive_anomalies > 1:
            reason = f"{conditions.consecutive_anomalies} consecutive {direction_str} anomalies detected"
        else:
            reason = f"Anomaly detected ({direction_str})"

        # Update cooldown tracker
        if conditions.cooldown_minutes > 0:
            self._last_alert_times[metric_name] = result.timestamp

        return True, reason


class BaseAlerter(ABC):
    """Abstract base class for all alerters.

    Alerters send notifications through various channels (Mattermost, Slack,
    Email, etc.). They handle message formatting, retry logic, and error handling.

    Alerters should NOT make decisions about whether to alert - that's
    AlertAnalyzer's job. Alerters just send messages.

    Example Implementation:
        >>> from detectk.base import BaseAlerter
        >>> from detectk.registry import AlerterRegistry
        >>>
        >>> @AlerterRegistry.register("mattermost")
        >>> class MattermostAlerter(BaseAlerter):
        ...     def __init__(self, config: dict[str, Any]) -> None:
        ...         self.config = config
        ...         self.webhook_url = config["webhook_url"]
        ...         self.validate_config(config)
        ...
        ...     def send(self, result: DetectionResult,
        ...              message: str | None = None) -> bool:
        ...         # Format message from template
        ...         # Send to webhook
        ...         # Handle retries
        ...         pass
    """

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize alerter with configuration.

        Args:
            config: Alerter configuration from YAML
                   Contains webhook URLs, templates, etc.

        Raises:
            ConfigurationError: If config is invalid
        """
        pass

    @abstractmethod
    def send(
        self,
        result: DetectionResult,
        message: str | None = None,
    ) -> bool:
        """Send alert for detected anomaly.

        This method should:
        1. Format message from template (if message not provided)
        2. Send to configured channel (webhook, API, SMTP, etc.)
        3. Handle retries with exponential backoff
        4. Return success status

        Args:
            result: Detection result to alert on
            message: Optional custom message (uses template if None)

        Returns:
            True if alert sent successfully (after retries if needed)

        Raises:
            AlertError: If sending fails after all retries

        Example:
            >>> alerter = MattermostAlerter(config)
            >>> result = DetectionResult(...)
            >>> success = alerter.send(result)
            >>> if success:
            ...     print("Alert sent!")
        """
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate alerter-specific configuration.

        Should check:
        - Required fields present (webhook_url, channel, etc.)
        - URLs valid
        - Message template valid
        - Credentials present (if needed)

        Args:
            config: Configuration dictionary to validate

        Raises:
            ConfigurationError: If config is invalid
        """
        pass

    def _format_message(
        self,
        result: DetectionResult,
        template: str,
    ) -> str:
        """Format alert message from template.

        Helper method for alerter implementations.
        Uses simple string formatting with result attributes.

        Args:
            result: Detection result
            template: Message template with {field} placeholders

        Returns:
            Formatted message

        Example:
            >>> template = "Alert! {metric_name} = {value:.2f}"
            >>> message = alerter._format_message(result, template)
            >>> print(message)
            Alert! sessions_10min = 850.00
        """
        try:
            return template.format(
                metric_name=result.metric_name,
                value=result.value,
                timestamp=result.timestamp,
                is_anomaly=result.is_anomaly,
                score=result.score,
                lower_bound=result.lower_bound if result.lower_bound else "N/A",
                upper_bound=result.upper_bound if result.upper_bound else "N/A",
                direction=result.direction if result.direction else "N/A",
                percent_deviation=result.percent_deviation if result.percent_deviation else "N/A",
            )
        except KeyError as e:
            raise AlertError(
                f"Invalid template placeholder: {e}",
                channel=self.__class__.__name__,
            )
