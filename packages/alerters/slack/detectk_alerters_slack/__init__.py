"""Slack alerter for DetectK.

Sends anomaly alerts to Slack channels via incoming webhooks.
"""

__version__ = "0.1.0"

from detectk_alerters_slack.alerter import SlackAlerter

__all__ = ["SlackAlerter"]
