# DetectK Quick Start Guide

Get started with DetectK in 5 minutes!

## Prerequisites

- Python 3.10+
- ClickHouse, PostgreSQL, or MySQL database
- (Optional) Mattermost or Slack webhook for alerts

## Installation

```bash
# Install core library with ClickHouse support
pip install detectk detectk-collectors-clickhouse detectk-detectors detectk-alerters-mattermost
```

## 5-Minute Tutorial

### Step 1: Create Your First Metric Configuration

Create `my_first_metric.yaml`:

```yaml
name: "sessions_10min"
description: "Monitor user sessions every 10 minutes"

# Data collection
collector:
  type: "clickhouse"
  params:
    host: "localhost"
    database: "analytics"
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL 10 minute) AS period_time,
        count(DISTINCT user_id) AS value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"

# Storage for historical data
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    database: "metrics"

# Anomaly detection
detector:
  type: "mad"  # Median Absolute Deviation - robust to outliers
  params:
    window_size: "30 days"
    n_sigma: 3.0

# Alerts
alerter:
  enabled: true
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    cooldown_minutes: 60

# Schedule
schedule:
  interval: "10 minutes"
```

### Step 2: Set Environment Variables

```bash
export MATTERMOST_WEBHOOK="https://your-mattermost.com/hooks/xxx"
```

### Step 3: Run Your First Check

```bash
# Validate configuration
dtk validate my_first_metric.yaml

# Run single check
dtk run my_first_metric.yaml
```

That's it! DetectK will:
1. Query your database for the last 10 minutes of data
2. Save to storage (dtk_datapoints table)
3. Load 30 days of historical data
4. Calculate median and MAD
5. Check if current value is anomalous
6. Send alert to Mattermost if anomaly detected

## Common Patterns

### Pattern 1: Simple Threshold Alert

```yaml
name: "api_errors"

collector:
  type: "clickhouse"
  params:
    query: |
      SELECT
        now() AS period_time,
        countIf(status_code >= 500) * 100.0 / count() AS value
      FROM api_logs
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detector:
  type: "threshold"
  params:
    operator: "greater_than"
    threshold: 1.0  # Alert if error rate > 1%

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
```

### Pattern 2: With Seasonality

```yaml
collector:
  params:
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL 10 minute) AS period_time,
        count() AS value,
        toHour(period_time) AS hour_of_day,  # Add seasonal feature
        toDayOfWeek(period_time) AS day_of_week
      FROM events
      WHERE timestamp >= '{{ period_start }}'
        AND timestamp < '{{ period_finish }}'
      GROUP BY period_time

    context_columns: ["hour_of_day", "day_of_week"]

detector:
  type: "mad"
  params:
    seasonal_features: ["hour_of_day", "day_of_week"]
    use_combined_seasonality: true  # Compare Monday 9AM with Monday 9AM only
```

### Pattern 3: Missing Data Detection

```yaml
collector:
  type: "clickhouse"
  params:
    query: |
      SELECT
        toStartOfInterval(now(), INTERVAL 5 minute) AS period_time,
        count() AS value
      FROM heartbeat_events
      WHERE timestamp >= now() - INTERVAL 5 minute

detector:
  type: "missing_data"
  params:
    max_staleness_minutes: 10  # Alert if no data for 10 minutes
```

## Historical Data Loading

Before running continuous monitoring, load historical data:

```yaml
# In your config, set:
schedule:
  start_time: "2024-01-01"
  end_time: "2024-03-01"
  interval: "10 minutes"
  batch_load_days: 30

alerter:
  enabled: false  # Don't spam during loading
```

Run:
```bash
dtk run my_first_metric.yaml
```

After loading complete:
- Remove `start_time` and `end_time`
- Set `alerter.enabled: true`
- Run continuously

## Scheduling

### Option 1: Cron (Simple)

```bash
# Every 10 minutes
*/10 * * * * /path/to/venv/bin/dtk run /path/to/config.yaml
```

### Option 2: Systemd Timer (Production)

Create `/etc/systemd/system/detectk-sessions.service`:

```ini
[Unit]
Description=DetectK Sessions Monitor

[Service]
Type=oneshot
User=detectk
WorkingDirectory=/opt/detectk
ExecStart=/opt/detectk/venv/bin/dtk run /opt/detectk/configs/sessions.yaml
Environment="MATTERMOST_WEBHOOK=https://..."
```

Create `/etc/systemd/system/detectk-sessions.timer`:

```ini
[Unit]
Description=Run DetectK Sessions Monitor every 10 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl enable detectk-sessions.timer
sudo systemctl start detectk-sessions.timer
```

### Option 3: Python Script (Custom)

```python
from detectk.check import MetricCheck
from datetime import datetime
import time

checker = MetricCheck()

while True:
    try:
        result = checker.execute("configs/sessions.yaml")

        if result.alert_sent:
            print(f"Alert sent: {result.alert_reason}")

        if result.errors:
            print(f"Errors: {result.errors}")

    except Exception as e:
        print(f"Error: {e}")

    time.sleep(600)  # 10 minutes
```

## Configuration Tips

### Use Environment Variables

```yaml
collector:
  params:
    host: "${CLICKHOUSE_HOST:-localhost}"  # Default if not set
    password: "${CLICKHOUSE_PASSWORD}"     # Required
    database: "${CLICKHOUSE_DB:-analytics}"
```

### Connection Profiles (Reusable)

Create `detectk_profiles.yaml`:

```yaml
clickhouse_prod:
  type: "clickhouse"
  host: "clickhouse.prod.example.com"
  port: 9000
  user: "detectk"
  password: "${CLICKHOUSE_PASSWORD}"
  database: "analytics"

mattermost_ops:
  type: "mattermost"
  webhook_url: "${MATTERMOST_WEBHOOK}"
  channel: "#ops-alerts"
```

Use in configs:

```yaml
collector:
  profile: "clickhouse_prod"
  params:
    query: |
      ...

alerter:
  profile: "mattermost_ops"
```

## Tuning Parameters

### Sensitivity

```yaml
detector:
  params:
    n_sigma: 3.0  # Standard
    # n_sigma: 2.5  # More sensitive (more alerts)
    # n_sigma: 4.0  # Less sensitive (fewer alerts)
```

### Alert Cooldown

```yaml
alerter:
  params:
    cooldown_minutes: 60  # Don't spam - wait 1 hour between alerts
```

### Window Size

```yaml
detector:
  params:
    window_size: "30 days"  # Standard
    # window_size: "7 days"   # Faster adaptation to new patterns
    # window_size: "90 days"  # More stable, slower adaptation
```

### Weighted Statistics

```yaml
detector:
  params:
    use_weighted: true
    exp_decay_factor: 0.1  # Higher = more weight to recent data
```

## Common Issues

### Issue: "No historical data found"

**Cause:** Storage table doesn't have data yet

**Solution:**
1. First run saves data to storage
2. Second run can do detection
3. Or load historical data first (see above)

### Issue: "Insufficient data in seasonal group"

**Cause:** Combined seasonality with short window

**Solution:**
- Increase `window_size` (e.g., 30 → 60 days)
- OR use `use_combined_seasonality: false` (separate mode)
- OR reduce number of seasonal features

### Issue: Too many false positives

**Solutions:**
1. Increase `n_sigma` (3.0 → 3.5 → 4.0)
2. Add seasonal features if patterns exist
3. Increase `cooldown_minutes`
4. Review metric - maybe it's naturally noisy

## Next Steps

- **Examples:** See `examples/` directory for more patterns
- **Seasonality:** Read `examples/seasonal/README.md` for advanced patterns
- **Production:** See `DEPLOYMENT.md` for production setup
- **Troubleshooting:** See `TROUBLESHOOTING.md` for common issues

## Getting Help

- **Documentation:** Full docs in `docs/` directory
- **Examples:** 20+ example configs in `examples/`
- **Issues:** https://github.com/alexeiveselov92/detectk/issues

## Full Example

Here's a complete production-ready config:

```yaml
name: "user_sessions_10min"
description: "Monitor active user sessions with hourly+weekly seasonality"

collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    port: 9000
    database: "analytics"
    user: "${CLICKHOUSE_USER}"
    password: "${CLICKHOUSE_PASSWORD}"

    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL 10 minute) AS period_time,
        count(DISTINCT user_id) AS value,
        toHour(period_time) AS hour_of_day,
        toDayOfWeek(period_time) AS day_of_week,
        if(toDayOfWeek(period_time) IN (6, 7), 1, 0) AS is_weekend
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"
    context_columns: ["hour_of_day", "day_of_week", "is_weekend"]

storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    database: "metrics"
    user: "${CLICKHOUSE_USER}"
    password: "${CLICKHOUSE_PASSWORD}"
    datapoints_retention_days: 90

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    use_weighted: true
    exp_decay_factor: 0.1
    seasonal_features: ["hour_of_day", "day_of_week"]
    use_combined_seasonality: true

alerter:
  enabled: true
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    channel: "#ops-alerts"
    username: "DetectK Monitor"
    cooldown_minutes: 60

  conditions:
    direction: "both"
    min_deviation_percent: 20

schedule:
  interval: "10 minutes"

metadata:
  team: "data-engineering"
  priority: "high"
  dashboards:
    - "https://grafana.example.com/d/sessions"
  runbook: "https://wiki.example.com/runbooks/sessions"
```

Run it:

```bash
# Set environment variables
export CLICKHOUSE_HOST="clickhouse.prod.example.com"
export CLICKHOUSE_USER="detectk"
export CLICKHOUSE_PASSWORD="your_secure_password"
export MATTERMOST_WEBHOOK="https://mattermost.example.com/hooks/xxx"

# Validate
dtk validate user_sessions_10min.yaml

# Run once
dtk run user_sessions_10min.yaml

# Schedule with cron
echo "*/10 * * * * cd /opt/detectk && /opt/detectk/venv/bin/dtk run configs/user_sessions_10min.yaml" | crontab -
```

**You're ready to monitor your metrics!** 🚀
