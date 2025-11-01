"""Mattermost alerter package for DetectK.

Simple alerter that sends formatted messages to Mattermost via webhooks.
Handles only: message formatting, sending, and cooldown (anti-spam).

Philosophy: Radical simplicity
- No AlertAnalyzer (unnecessary abstraction)
- No consecutive checking (detector's job)
- No direction filtering (detector's job)
- No min deviation thresholds (detector's job)
- Only cooldown to prevent spam
"""

__version__ = "0.1.0"

# Import for auto-registration
from detectk_alerters_mattermost.alerter import MattermostAlerter

__all__ = [
    "__version__",
    "MattermostAlerter",
]
