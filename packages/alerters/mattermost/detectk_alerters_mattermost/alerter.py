"""Mattermost alerter for DetectK.

Sends alert messages to Mattermost channels via incoming webhooks.

Philosophy: Keep it simple!
- Alerter only handles: formatting + sending + cooldown (anti-spam)
- Detector handles: what is anomaly, thresholds, direction, etc.
- No complex state tracking, no consecutive checking, no direction filtering
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from detectk.base import BaseAlerter
from detectk.exceptions import AlertError, ConfigurationError
from detectk.models import DetectionResult
from detectk.registry import AlerterRegistry

logger = logging.getLogger(__name__)


@AlerterRegistry.register("mattermost")
class MattermostAlerter(BaseAlerter):
    """Simple alerter that sends messages to Mattermost via webhooks.

    Responsibilities:
    1. Format detection results as readable messages
    2. Send to Mattermost webhook
    3. Prevent spam via cooldown

    NOT responsible for:
    - Deciding what is anomalous (detector's job)
    - Filtering by direction (use appropriate detector)
    - Consecutive anomaly checking (tune detector instead)
    - Min deviation thresholds (tune detector n_sigma)

    Configuration:
        webhook_url: Mattermost incoming webhook URL (required)
        cooldown_minutes: Minutes to wait between alerts for same metric (default: 60)
        username: Bot username to display (default: "DetectK")
        icon_url: Bot icon URL (optional)
        channel: Channel override (optional, uses webhook default)
        timeout: Request timeout in seconds (default: 10)
        message_template: Custom Jinja2 template for message formatting (optional)

    Example configuration:
        alerter:
          type: "mattermost"
          params:
            webhook_url: "${MATTERMOST_WEBHOOK}"
            cooldown_minutes: 60  # Don't spam - wait 1 hour between alerts
            username: "DetectK Bot"

    Example with custom message template (Jinja2):
        alerter:
          type: "mattermost"
          params:
            webhook_url: "${MATTERMOST_WEBHOOK}"
            cooldown_minutes: 60
            message_template: |
              🚨 **ANOMALY** `{{ metric_name }}`

              Value: {{ value | round(2) }}
              {% if lower_bound and upper_bound %}
              Expected: [{{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}]
              {% endif %}

              {{ timestamp.strftime('%Y-%m-%d %H:%M:%S') }}

    Default message format (if no custom template):
        🚨 **ANOMALY DETECTED** `metric_name`

        📊 **Value:** 1,234.5 (↗ up)
        📈 **Expected:** [900.0 - 1,100.0]
        📉 **Score:** 4.2 sigma
        ⚠️ **Deviation:** +15.0%

        🕒 2024-11-01 23:50:00
        🔍 Detector: mad (window: 30 days, n_sigma: 3.0)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Mattermost alerter.

        Args:
            config: Alerter configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config = config
        self.validate_config(config)

        # Required
        self.webhook_url = config["webhook_url"]

        # Optional with defaults
        self.cooldown_minutes = config.get("cooldown_minutes", 60)
        self.username = config.get("username", "DetectK")
        self.icon_url = config.get("icon_url")
        self.channel = config.get("channel")
        self.timeout = config.get("timeout", 10)

        # Custom message template (Jinja2)
        self.message_template = config.get("message_template")
        self._template = None
        if self.message_template:
            from jinja2 import Template, TemplateSyntaxError

            try:
                self._template = Template(self.message_template)
            except TemplateSyntaxError as e:
                raise ConfigurationError(
                    f"Invalid Jinja2 template in message_template: {e}",
                    config_path="alerter.params.message_template",
                ) from e

        # Cooldown tracking (in-memory for now, Phase 3: move to storage)
        self._last_alert_time: dict[str, datetime] = {}

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate alerter configuration.

        Args:
            config: Configuration to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if "webhook_url" not in config:
            raise ConfigurationError(
                "Mattermost alerter requires 'webhook_url' parameter",
                config_path="alerter.params",
            )

        webhook_url = config["webhook_url"].strip()
        if not webhook_url:
            raise ConfigurationError(
                "Mattermost webhook_url cannot be empty",
                config_path="alerter.params.webhook_url",
            )

        if not webhook_url.startswith(("http://", "https://")):
            raise ConfigurationError(
                f"Invalid webhook URL: {webhook_url}. Must start with http:// or https://",
                config_path="alerter.params.webhook_url",
            )

        # Validate cooldown if specified
        cooldown = config.get("cooldown_minutes", 60)
        if not isinstance(cooldown, (int, float)) or cooldown < 0:
            raise ConfigurationError(
                f"cooldown_minutes must be non-negative number, got {cooldown}",
                config_path="alerter.params.cooldown_minutes",
            )

    def send(self, detection: DetectionResult, message: str | None = None) -> bool:
        """Send alert to Mattermost if conditions are met.

        Conditions checked:
        1. Is anomaly detected? (from detector)
        2. Is cooldown period expired?

        Args:
            detection: Detection result to alert on
            message: Optional custom message (if None, auto-generates)

        Returns:
            True if alert was sent, False if skipped

        Raises:
            AlertError: If sending fails
        """
        # Check 1: Is this anomalous?
        if not detection.is_anomaly:
            logger.debug(f"Skipping alert for {detection.metric_name}: not anomalous")
            return False

        # Check 2: Cooldown
        if self._in_cooldown(detection.metric_name, detection.timestamp):
            logger.debug(
                f"Skipping alert for {detection.metric_name}: in cooldown period"
            )
            return False

        # Generate message if not provided
        if message is None:
            message = self._format_message(detection)

        # Send to Mattermost
        try:
            self._send_webhook(message)

            # Update cooldown tracker
            self._last_alert_time[detection.metric_name] = detection.timestamp

            logger.info(f"Alert sent for {detection.metric_name}")
            return True

        except Exception as e:
            raise AlertError(
                f"Failed to send Mattermost alert for {detection.metric_name}: {e}",
                alerter_type="mattermost",
            ) from e

    def _in_cooldown(self, metric_name: str, current_time: datetime) -> bool:
        """Check if metric is in cooldown period.

        Args:
            metric_name: Metric name
            current_time: Current detection timestamp

        Returns:
            True if in cooldown, False otherwise
        """
        if self.cooldown_minutes == 0:
            return False  # Cooldown disabled

        if metric_name not in self._last_alert_time:
            return False  # No previous alert

        last_alert = self._last_alert_time[metric_name]
        elapsed = current_time - last_alert
        cooldown_period = timedelta(minutes=self.cooldown_minutes)

        return elapsed < cooldown_period

    def _format_message(self, detection: DetectionResult) -> str:
        """Format detection result as Mattermost message.

        Uses custom template if provided, otherwise uses default format.

        Args:
            detection: Detection result

        Returns:
            Formatted message with Markdown
        """
        # If custom template provided, use it
        if self._template:
            try:
                return self._template.render(
                    metric_name=detection.metric_name,
                    timestamp=detection.timestamp,
                    value=detection.value,
                    is_anomaly=detection.is_anomaly,
                    score=detection.score,
                    lower_bound=detection.lower_bound,
                    upper_bound=detection.upper_bound,
                    direction=detection.direction,
                    percent_deviation=detection.percent_deviation,
                    metadata=detection.metadata or {},
                )
            except Exception as e:
                # If template rendering fails, log error and use default format
                logger.error(f"Failed to render custom template: {e}. Using default format.")
                # Fall through to default format

        # Default format
        return self._format_default_message(detection)

    def _format_default_message(self, detection: DetectionResult) -> str:
        """Format detection result using default template.

        Args:
            detection: Detection result

        Returns:
            Formatted message with Markdown
        """
        # Direction emoji
        direction_emoji = {
            "up": "↗",
            "down": "↘",
            None: "→",
        }.get(detection.direction, "→")

        # Build message lines
        lines = [
            f"🚨 **ANOMALY DETECTED** `{detection.metric_name}`",
            "",
        ]

        # Value and direction
        direction_text = detection.direction or "unknown"
        lines.append(
            f"📊 **Value:** {detection.value:,.2f} ({direction_emoji} {direction_text})"
        )

        # Expected bounds (if available)
        if detection.lower_bound is not None and detection.upper_bound is not None:
            lines.append(
                f"📈 **Expected:** [{detection.lower_bound:,.2f} - {detection.upper_bound:,.2f}]"
            )

        # Anomaly score
        if detection.score is not None:
            if detection.score == float("inf"):
                lines.append("📉 **Score:** ∞ (extreme outlier)")
            else:
                lines.append(f"📉 **Score:** {detection.score:.2f} sigma")

        # Percent deviation
        if detection.percent_deviation is not None:
            lines.append(f"⚠️ **Deviation:** {detection.percent_deviation:+.1f}%")

        # Timestamp
        lines.append("")
        lines.append(
            f"🕒 {detection.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Detector info from metadata
        if detection.metadata:
            detector_parts = []

            if "detector" in detection.metadata:
                detector_parts.append(detection.metadata["detector"])

            if "window_size" in detection.metadata:
                detector_parts.append(f"window: {detection.metadata['window_size']}")

            if "n_sigma" in detection.metadata:
                detector_parts.append(f"n_sigma: {detection.metadata['n_sigma']}")

            if detector_parts:
                lines.append(f"🔍 **Detector:** {', '.join(detector_parts)}")

        return "\n".join(lines)

    def _send_webhook(self, message: str) -> None:
        """Send message to Mattermost webhook.

        Args:
            message: Message text (Markdown supported)

        Raises:
            requests.RequestException: If request fails
        """
        payload = {
            "text": message,
            "username": self.username,
        }

        if self.icon_url:
            payload["icon_url"] = self.icon_url

        if self.channel:
            payload["channel"] = self.channel

        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=self.timeout,
        )

        response.raise_for_status()

        logger.debug(
            f"Mattermost webhook response: {response.status_code}"
        )

    def clear_cooldown(self, metric_name: str | None = None) -> None:
        """Clear cooldown tracking for a metric or all metrics.

        Useful for testing or manual reset.

        Args:
            metric_name: Metric to clear (if None, clear all)
        """
        if metric_name is None:
            self._last_alert_time.clear()
        else:
            self._last_alert_time.pop(metric_name, None)
