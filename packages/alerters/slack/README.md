# DetectK Slack Alerter

Send anomaly detection alerts to Slack channels via incoming webhooks.

## Installation

```bash
pip install detectk-alerters-slack
```

## Quick Start

### 1. Create Slack Incoming Webhook

1. Go to your Slack workspace → Apps → Incoming Webhooks
2. Click "Add to Slack"
3. Choose channel and click "Add Incoming Webhooks Integration"
4. Copy the Webhook URL (https://hooks.slack.com/services/...)

### 2. Set Environment Variable

```bash
export SLACK_WEBHOOK="https://hooks.slack.com/services/T00000000/B00000000/XXXX"
```

### 3. Configure DetectK

```yaml
name: "sessions_hourly"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    query: "SELECT count() as value FROM sessions"

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

alerter:
  type: "slack"  # ← Slack alerter
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    cooldown_minutes: 60
```

### 4. Run

```bash
dtk run your_config.yaml
```

## Configuration

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `webhook_url` | string | Slack incoming webhook URL (required) |

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cooldown_minutes` | int | 60 | Minutes to wait between alerts for same metric |
| `username` | string | "DetectK" | Bot username displayed in Slack |
| `icon_emoji` | string | ":warning:" | Bot icon emoji (e.g., ":bell:", ":alert:") |
| `icon_url` | string | None | Bot icon URL (overrides icon_emoji if set) |
| `channel` | string | None | Channel override (e.g., "#alerts", "@username") |
| `timeout` | int | 10 | HTTP request timeout in seconds |
| `message_template` | string | None | Custom Jinja2 template for formatting (optional) |

### Example with All Options

```yaml
alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    cooldown_minutes: 120
    username: "Anomaly Bot"
    icon_emoji: ":rotating_light:"
    channel: "#critical-alerts"
    timeout: 15
```

## Default Message Format

Simple, professional, no emojis (works everywhere):

```
*ANOMALY DETECTED: sessions_hourly*

Value: 1234.50
Expected range: 900.00 - 1100.00
Anomaly score: 4.20 sigma
Direction: up
Deviation: +15.0%

Time: 2024-11-02 14:30:00
Detector: type=mad, window=30 days, threshold=3.0 sigma
```

**Why no emojis in default?**
- ✅ Works everywhere (Slack, email, SMS, logs)
- ✅ Accessible to screen readers
- ✅ Professional appearance
- ✅ Plain text with Slack mrkdwn (Markdown)

**Want emojis?** Use custom templates (see below).

## Custom Message Templates

Customize alerts using Jinja2 templates:

### Simple Custom Template

```yaml
alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    message_template: |
      :warning: *ALERT* `{{ metric_name }}`
      Value: {{ value | round(2) }}
      Expected: {{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}
      Time: {{ timestamp.strftime('%H:%M:%S') }}
```

### Rich Format with Emojis

```yaml
alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    message_template: |
      :rotating_light: *ANOMALY DETECTED* `{{ metric_name }}`

      :chart_with_upwards_trend: *Value:* {{ value | round(2) }}{% if direction %} ({{ direction }}){% endif %}

      {% if lower_bound and upper_bound %}
      :arrow_up_down: *Expected:* {{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}
      {% endif %}
      {% if score %}
      :dart: *Score:* {{ score | round(2) }} sigma
      {% endif %}

      :clock3: *Time:* {{ timestamp.strftime('%Y-%m-%d %H:%M:%S') }}
```

### Severity-Based Formatting

```yaml
alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    message_template: |
      {% if score and score >= 5.0 %}
      :red_circle: *CRITICAL* `{{ metric_name }}` <!channel>
      {% elif score and score >= 4.0 %}
      :large_orange_diamond: *HIGH* `{{ metric_name }}`
      {% else %}
      :large_yellow_diamond: *MODERATE* `{{ metric_name }}`
      {% endif %}

      Value: {{ value | round(2) }}
      Score: {{ score | round(1) }} sigma
```

### Available Template Variables

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `metric_name` | string | Metric name | `"sessions_hourly"` |
| `timestamp` | datetime | Detection time | `datetime(2024, 11, 2, 14, 30)` |
| `value` | float | Current value | `1500.0` |
| `is_anomaly` | bool | Anomaly status | `True` |
| `score` | float \| None | Anomaly score (sigma) | `4.2` |
| `lower_bound` | float \| None | Expected min | `900.0` |
| `upper_bound` | float \| None | Expected max | `1100.0` |
| `direction` | str \| None | Direction | `"up"` / `"down"` / `None` |
| `percent_deviation` | float \| None | % deviation | `36.4` |
| `metadata` | dict | Detector info | `{"detector": "mad", ...}` |

## Cooldown Behavior

Prevents alert spam for the same metric:

- **First anomaly**: Alert sent immediately ✅
- **Subsequent anomalies** (within cooldown period): Skipped ⏭️
- **After cooldown expires**: Alert sent again ✅

**Example with cooldown_minutes=60:**
```
10:00 - Anomaly detected → Alert sent ✅
10:30 - Anomaly detected → Skipped (in cooldown) ⏭️
10:45 - Anomaly detected → Skipped (in cooldown) ⏭️
11:15 - Anomaly detected → Alert sent ✅ (cooldown expired)
```

**Disable cooldown:** Set `cooldown_minutes: 0` (not recommended - will spam)

## Slack vs Mattermost

Both are very similar (webhook-based), with minor differences:

| Feature | Slack | Mattermost |
|---------|-------|------------|
| Webhook URL format | `https://hooks.slack.com/services/...` | Any HTTPS URL |
| Markdown flavor | Slack mrkdwn | Standard Markdown |
| Bold syntax | `*bold*` | `**bold**` |
| Icon | `icon_emoji` or `icon_url` | `icon_url` only |
| Channel override | `#channel` or `@user` | `#channel` |

**Recommendation:** Use Mattermost if self-hosted, Slack if using Slack workspace.

## Troubleshooting

### No alerts sent

1. **Check webhook URL is correct:**
   ```bash
   curl -X POST -H 'Content-Type: application/json' \
     -d '{"text":"Test message"}' \
     https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

2. **Check if anomalies detected:**
   - Enable storage: `storage.enabled: true`
   - Query: `SELECT * FROM dtk_detections WHERE metric_name = 'your_metric' ORDER BY detected_at DESC LIMIT 10;`

3. **Check cooldown:**
   - Reduce `cooldown_minutes` for testing (e.g., 5 minutes)
   - Or disable: `cooldown_minutes: 0`

4. **Check detector sensitivity:**
   - Lower `n_sigma` for more alerts (e.g., 3.0 → 2.5)
   - Shorter `window_size` for faster adaptation

### Webhook errors

**401 Unauthorized:**
- Webhook URL is invalid or expired
- Regenerate webhook in Slack settings

**404 Not Found:**
- Webhook URL format is incorrect
- Must start with `https://hooks.slack.com/services/`

**Channel not found:**
- Channel override is invalid
- Use `#channel-name` format, not `channel-name`

**Rate limiting:**
- Slack has rate limits (1 message per second per webhook)
- Increase `cooldown_minutes` to avoid hitting limits

## Best Practices

1. **Start conservative:**
   - High `n_sigma` (4.0+) to avoid alert fatigue
   - Long cooldown (60+ minutes) for frequent checks

2. **Use channel mentions sparingly:**
   - Only for critical alerts (score >= 5.0)
   - Avoid `<!channel>` or `<!here>` for non-critical

3. **Test in development channel first:**
   - Create `#detectk-testing` channel
   - Test configuration before production deployment

4. **Monitor alert frequency:**
   - Too many alerts = tune detector parameters
   - Too few alerts = lower n_sigma threshold

5. **Use templates for readability:**
   - Add context-specific info (runbooks, dashboards)
   - Include team-specific formatting preferences

## Examples

See [examples/slack/](../../examples/slack/) for full working examples:
- `simple_alert.yaml` - Basic MAD detector + Slack
- `rich_format.yaml` - Alert with emojis and visual formatting
- `severity_based.yaml` - Conditional formatting by severity
- `multi_detector.yaml` - Multiple detectors with single alert

## See Also

- [Mattermost Alerter](../mattermost/) - Similar webhook-based alerter
- [Telegram Alerter](../telegram/) - Bot-based alerter for Telegram
- [Email Alerter](../email/) - SMTP email alerts
- [DetectK Documentation](https://github.com/alexeiveselov92/detectk)
