"""Tests for MattermostAlerter."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
import requests_mock

from detectk.exceptions import AlertError, ConfigurationError
from detectk.models import DetectionResult
from detectk_alerters_mattermost import MattermostAlerter


def test_mattermost_alerter_registration() -> None:
    """Test that MattermostAlerter is registered."""
    from detectk.registry import AlerterRegistry

    assert AlerterRegistry.is_registered("mattermost")
    assert AlerterRegistry.get("mattermost") == MattermostAlerter


def test_mattermost_alerter_init() -> None:
    """Test alerter initialization."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx"}
    alerter = MattermostAlerter(config)

    assert alerter.webhook_url == "https://mattermost.example.com/hooks/xxx"
    assert alerter.cooldown_minutes == 60  # default
    assert alerter.username == "DetectK"  # default


def test_mattermost_alerter_missing_webhook() -> None:
    """Test error when webhook_url missing."""
    with pytest.raises(ConfigurationError, match="webhook_url.*parameter"):
        MattermostAlerter({})


def test_mattermost_alerter_invalid_webhook() -> None:
    """Test error when webhook_url invalid."""
    with pytest.raises(ConfigurationError, match="Invalid webhook URL"):
        MattermostAlerter({"webhook_url": "not-a-url"})


def test_send_alert_anomaly() -> None:
    """Test sending alert for anomaly."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx", "cooldown_minutes": 0}
    alerter = MattermostAlerter(config)

    detection = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime.now(),
        value=150.0,
        is_anomaly=True,
        score=4.2,
        lower_bound=90.0,
        upper_bound=110.0,
        direction="up",
        percent_deviation=36.4,
    )

    with requests_mock.Mocker() as m:
        m.post("https://mattermost.example.com/hooks/xxx", text="ok")
        result = alerter.send(detection)

    assert result is True
    assert m.call_count == 1


def test_send_alert_not_anomaly() -> None:
    """Test skipping alert when not anomalous."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx"}
    alerter = MattermostAlerter(config)

    detection = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime.now(),
        value=100.0,
        is_anomaly=False,
        score=1.5,
    )

    result = alerter.send(detection)
    assert result is False


def test_send_alert_cooldown() -> None:
    """Test cooldown preventing duplicate alerts."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx", "cooldown_minutes": 60}
    alerter = MattermostAlerter(config)

    detection1 = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime.now(),
        value=150.0,
        is_anomaly=True,
        score=4.2,
    )

    detection2 = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime.now() + timedelta(minutes=30),  # Only 30 min later
        value=160.0,
        is_anomaly=True,
        score=4.5,
    )

    with requests_mock.Mocker() as m:
        m.post("https://mattermost.example.com/hooks/xxx", text="ok")

        # First alert sent
        result1 = alerter.send(detection1)
        assert result1 is True

        # Second alert skipped (cooldown)
        result2 = alerter.send(detection2)
        assert result2 is False

    assert m.call_count == 1  # Only one request


def test_send_alert_cooldown_expired() -> None:
    """Test alert sent after cooldown expires."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx", "cooldown_minutes": 60}
    alerter = MattermostAlerter(config)

    detection1 = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime.now(),
        value=150.0,
        is_anomaly=True,
        score=4.2,
    )

    detection2 = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime.now() + timedelta(minutes=61),  # 61 min later
        value=160.0,
        is_anomaly=True,
        score=4.5,
    )

    with requests_mock.Mocker() as m:
        m.post("https://mattermost.example.com/hooks/xxx", text="ok")

        result1 = alerter.send(detection1)
        assert result1 is True

        result2 = alerter.send(detection2)
        assert result2 is True  # Cooldown expired

    assert m.call_count == 2


def test_format_message() -> None:
    """Test message formatting."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx"}
    alerter = MattermostAlerter(config)

    detection = DetectionResult(
        metric_name="test_metric",
        timestamp=datetime(2024, 11, 1, 23, 50, 0),
        value=150.0,
        is_anomaly=True,
        score=4.2,
        lower_bound=90.0,
        upper_bound=110.0,
        direction="up",
        percent_deviation=36.4,
        metadata={"detector": "mad", "window_size": "30 days", "n_sigma": 3.0},
    )

    message = alerter._format_message(detection)

    assert "ANOMALY DETECTED" in message
    assert "test_metric" in message
    assert "150.00" in message
    assert "up" in message or "↗" in message
    assert "90.00 - 110.00" in message  # Range without brackets
    assert "4.2" in message
    assert "+36.4%" in message
    assert "2024-11-01 23:50:00" in message
    assert "mad" in message


def test_clear_cooldown() -> None:
    """Test cooldown clearing."""
    config = {"webhook_url": "https://mattermost.example.com/hooks/xxx"}
    alerter = MattermostAlerter(config)

    alerter._last_alert_time["metric1"] = datetime.now()
    alerter._last_alert_time["metric2"] = datetime.now()

    # Clear specific metric
    alerter.clear_cooldown("metric1")
    assert "metric1" not in alerter._last_alert_time
    assert "metric2" in alerter._last_alert_time

    # Clear all
    alerter.clear_cooldown()
    assert len(alerter._last_alert_time) == 0
