# DetectK Troubleshooting Guide

This guide helps you diagnose and fix common issues with DetectK.

---

## Table of Contents

1. [Configuration Issues](#configuration-issues)
2. [Collection Issues](#collection-issues)
3. [Detection Issues](#detection-issues)
4. [Alert Issues](#alert-issues)
5. [Storage Issues](#storage-issues)
6. [Performance Issues](#performance-issues)
7. [Debugging Tips](#debugging-tips)

---

## Configuration Issues

### Error: "ConfigurationError: Invalid configuration"

**Symptoms:**
```
detectk.exceptions.ConfigurationError: Invalid configuration: ...
```

**Causes:**
1. YAML syntax error
2. Missing required fields
3. Invalid parameter values
4. Environment variable not set

**Solutions:**

1. **Validate YAML syntax:**
```bash
# Use dtk validate command
dtk validate configs/my_metric.yaml

# Or use Python YAML parser
python -c "import yaml; yaml.safe_load(open('configs/my_metric.yaml'))"
```

2. **Check required fields:**
```yaml
# Minimum required configuration:
name: "my_metric"

collector:
  type: "clickhouse"
  params:
    query: "..."  # Must include {{ period_start }} and {{ period_finish }}
    timestamp_column: "period_time"
    value_column: "value"

detector:
  type: "threshold"
  params:
    threshold: 100

schedule:
  interval: "10 minutes"
```

3. **Check environment variables:**
```bash
# List all env vars DetectK needs
grep -r '\${' configs/my_metric.yaml

# Set missing variables
export CLICKHOUSE_HOST="localhost"
export CLICKHOUSE_PASSWORD="secret"

# Or use defaults
# ${VAR_NAME:-default_value}
```

4. **Enable verbose logging:**
```bash
dtk run configs/my_metric.yaml --verbose
```

---

### Error: "SQL query must use Jinja2 variable {{ period_start }}"

**Symptoms:**
```
detectk.exceptions.ConfigurationError: SQL query must use Jinja2 variable {{ period_start }}
```

**Cause:** Query doesn't include required time range variables.

**Solution:** Add time range filter to query:

```yaml
# ❌ Wrong (no time range)
collector:
  params:
    query: |
      SELECT count() as value
      FROM events

# ✅ Correct (with time range)
collector:
  params:
    query: |
      SELECT count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**Why required:** DetectK uses time series architecture. Every query must accept time range parameters.

---

### Error: "KeyError: 'CLICKHOUSE_PASSWORD'"

**Symptoms:**
```
KeyError: 'CLICKHOUSE_PASSWORD'
```

**Cause:** Required environment variable not set.

**Solutions:**

1. **Set environment variable:**
```bash
export CLICKHOUSE_PASSWORD="your_password"
```

2. **Use default value in config:**
```yaml
collector:
  params:
    password: "${CLICKHOUSE_PASSWORD:-}"  # Empty string if not set
```

3. **Use connection profile:**
```yaml
# detectk_profiles.yaml
clickhouse_prod:
  type: "clickhouse"
  host: "localhost"
  password: "hardcoded_password"  # Not recommended, but works

# In metric config:
collector:
  profile: "clickhouse_prod"
  params:
    query: "..."
```

---

## Collection Issues

### Error: "CollectionError: Failed to execute query"

**Symptoms:**
```
detectk.exceptions.CollectionError: Failed to execute query: ...
```

**Common causes:**

#### 1. Database Connection Failed

**Error message:**
```
Failed to connect to localhost:9000
```

**Solutions:**
```bash
# Check if ClickHouse is running
clickhouse-client --query "SELECT 1"

# Check connection parameters
dtk run configs/my_metric.yaml --verbose

# Test connection manually
clickhouse-client --host localhost --port 9000 --user default --password secret
```

#### 2. SQL Syntax Error

**Error message:**
```
Syntax error: unexpected token "FORM"
```

**Solutions:**
```bash
# Test query manually in ClickHouse
clickhouse-client --query "
  SELECT count() as value
  FROM events
  WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
"

# Check Jinja2 rendering
dtk run configs/my_metric.yaml --verbose  # Shows rendered query
```

#### 3. Table/Column Doesn't Exist

**Error message:**
```
Table default.events doesn't exist
```

**Solutions:**
```bash
# List tables
clickhouse-client --query "SHOW TABLES"

# Check table schema
clickhouse-client --query "DESCRIBE events"

# Fix table/column names in query
```

#### 4. Permissions Issue

**Error message:**
```
Not enough privileges
```

**Solutions:**
```sql
-- Grant read permissions
GRANT SELECT ON database.table TO user;

-- Check current user permissions
SHOW GRANTS FOR CURRENT_USER;
```

---

### Error: "Query returned no data"

**Symptoms:**
```
CollectionError: Query returned no data
```

**Causes:**
1. No data in time range
2. Wrong time filter
3. Wrong table/database

**Solutions:**

1. **Check if data exists:**
```sql
-- In ClickHouse
SELECT
    min(timestamp) as earliest,
    max(timestamp) as latest,
    count() as total_rows
FROM events;
```

2. **Test query manually:**
```sql
SELECT count() as value
FROM events
WHERE timestamp >= now() - INTERVAL 1 HOUR
  AND timestamp < now();
```

3. **Enable verbose logging:**
```bash
dtk run configs/my_metric.yaml --verbose
# Shows: "Query returned 0 rows for period ..."
```

4. **Adjust time range:**
```yaml
# Try longer interval if data is sparse
schedule:
  interval: "1 hour"  # Instead of 10 minutes
```

---

### Error: "Query returned multiple rows but no aggregation"

**Symptoms:**
```
CollectionError: Expected single value, got 5 rows
```

**Cause:** Query returns multiple rows without grouping by time.

**Solution:** Add `GROUP BY` with time interval:

```yaml
# ❌ Wrong (returns multiple rows per period)
query: |
  SELECT value
  FROM metrics
  WHERE timestamp >= '{{ period_start }}'

# ✅ Correct (aggregates into single value per period)
query: |
  SELECT
    toStartOfInterval(timestamp, INTERVAL 10 minute) AS period_time,
    avg(value) AS value
  FROM metrics
  WHERE timestamp >= toDateTime('{{ period_start }}')
    AND timestamp < toDateTime('{{ period_finish }}')
  GROUP BY period_time
  ORDER BY period_time
```

---

## Detection Issues

### Error: "DetectionError: No historical data found"

**Symptoms:**
```
detectk.exceptions.DetectionError: No historical data found for metric 'sessions_10min'
```

**Cause:** Storage doesn't have enough historical data yet.

**Solutions:**

1. **First run saves data, second run detects:**
```bash
# First run - collects and saves
dtk run configs/sessions.yaml

# Wait for next interval...

# Second run - has history now
dtk run configs/sessions.yaml
```

2. **Load historical data:**
```yaml
# In config, set schedule with start_time
schedule:
  start_time: "2024-01-01"
  end_time: "2024-02-01"  # Optional, defaults to now
  interval: "10 minutes"

alerter:
  enabled: false  # Don't send alerts during load
```

Run:
```bash
dtk run configs/sessions.yaml
# Loads data from 2024-01-01 to now
```

After loading, remove `start_time` and enable alerter.

3. **Check storage has data:**
```sql
-- ClickHouse
SELECT
    count() as total_points,
    min(collected_at) as earliest,
    max(collected_at) as latest
FROM dtk_datapoints
WHERE metric_name = 'sessions_10min';
```

---

### Error: "Insufficient data in seasonal group"

**Symptoms:**
```
DetectionError: Insufficient data in seasonal group: 2 points (minimum 3 required)
```

**Cause:** Combined seasonality with insufficient history.

**Example:**
- Seasonal features: `[hour_of_day, day_of_week]`
- Combined mode: Compares Monday 14:00 only with other Monday 14:00
- If window = 7 days, only 1 Monday 14:00 exists → insufficient

**Solutions:**

1. **Increase window size:**
```yaml
detector:
  params:
    window_size: "30 days"  # Instead of 7 days
```

2. **Use separate seasonality (OR mode):**
```yaml
detector:
  params:
    seasonal_features: ["hour_of_day", "day_of_week"]
    use_combined_seasonality: false  # OR mode - more data
```

3. **Reduce seasonal features:**
```yaml
# ❌ Too granular
seasonal_features: ["hour_of_day", "day_of_week", "day_of_month"]

# ✅ Less granular
seasonal_features: ["hour_of_day"]
```

4. **Wait for more data:**
```bash
# Check how much data you have
SELECT
    count() as points,
    dateDiff('day', min(collected_at), max(collected_at)) as days_of_data
FROM dtk_datapoints
WHERE metric_name = 'sessions_10min';
```

**See also:** [Seasonal examples](examples/seasonal/README.md)

---

### False Positives (Too Many Alerts)

**Symptoms:**
- Alerts for normal variations
- Alerts during known events (deployments, weekends, etc.)

**Solutions:**

1. **Increase n_sigma (less sensitive):**
```yaml
detector:
  params:
    n_sigma: 4.0  # Instead of 3.0 (fewer alerts)
```

2. **Add seasonal features:**
```yaml
# If Monday 9AM is different from Saturday 9AM
detector:
  params:
    seasonal_features: ["hour_of_day", "day_of_week"]
    use_combined_seasonality: true
```

3. **Increase cooldown:**
```yaml
alerter:
  params:
    cooldown_minutes: 120  # 2 hours instead of 60
```

4. **Add minimum deviation threshold:**
```yaml
alerter:
  conditions:
    min_deviation_percent: 20  # Only alert if >20% deviation
```

5. **Use weighted statistics:**
```yaml
detector:
  params:
    use_weighted: true
    exp_decay_factor: 0.15  # More weight to recent data
```

---

### False Negatives (Missed Incidents)

**Symptoms:**
- Real incidents not detected
- Alerts sent too late

**Solutions:**

1. **Decrease n_sigma (more sensitive):**
```yaml
detector:
  params:
    n_sigma: 2.5  # Instead of 3.0 (more alerts)
```

2. **Review seasonal grouping:**
```yaml
# Maybe you're comparing wrong periods?
# Try opposite mode:
detector:
  params:
    use_combined_seasonality: false  # Switch from true
```

3. **Reduce window size (faster adaptation):**
```yaml
detector:
  params:
    window_size: "7 days"  # Instead of 30 days
```

4. **Check if data quality issues:**
```sql
-- Are there outliers in history?
SELECT
    percentile(value, 0.01) as p01,
    percentile(value, 0.50) as median,
    percentile(value, 0.99) as p99,
    max(value) as max_value
FROM dtk_datapoints
WHERE metric_name = 'sessions_10min';
```

---

## Alert Issues

### Error: "AlertError: Failed to send alert"

**Symptoms:**
```
detectk.exceptions.AlertError: Failed to send alert to Mattermost: ...
```

**Common causes:**

#### 1. Invalid Webhook URL

**Error:**
```
404 Not Found
```

**Solutions:**
```bash
# Test webhook manually
curl -X POST "${MATTERMOST_WEBHOOK}" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message"}'

# Check webhook in config
dtk run configs/my_metric.yaml --verbose
```

#### 2. Network/Firewall Issue

**Error:**
```
Connection timeout
```

**Solutions:**
```bash
# Test network connectivity
curl -v "${MATTERMOST_WEBHOOK}"

# Check firewall rules
# Allow outbound HTTPS (port 443)
```

#### 3. Webhook Disabled/Deleted

**Error:**
```
401 Unauthorized
```

**Solution:** Regenerate webhook in Mattermost/Slack settings.

---

### Alerts Not Being Sent

**Symptoms:**
- Detector finds anomaly but no alert sent
- No errors, just silence

**Common causes:**

1. **Alerter disabled:**
```yaml
alerter:
  enabled: false  # ← Check this!
```

2. **Cooldown period active:**
```bash
# Check last alert time
SELECT
    metric_name,
    detected_at,
    alert_sent,
    alert_reason
FROM dtk_detections
WHERE metric_name = 'sessions_10min'
  AND alert_sent = 1
ORDER BY detected_at DESC
LIMIT 5;
```

If last alert was sent <60 minutes ago (default cooldown), new alerts are suppressed.

3. **Alert conditions not met:**
```yaml
alerter:
  conditions:
    direction: "up"  # Only alerts on increases, not decreases
    min_deviation_percent: 20  # Must be >20% deviation
```

Check if anomaly meets these conditions.

4. **Enable verbose logging:**
```bash
dtk run configs/my_metric.yaml --verbose
# Shows: "Alert suppressed: cooldown active (last alert 45 minutes ago)"
```

---

## Storage Issues

### Error: "StorageError: Failed to save datapoint"

**Symptoms:**
```
detectk.exceptions.StorageError: Failed to save datapoint: ...
```

**Common causes:**

#### 1. Table Doesn't Exist

**Error:**
```
Table default.dtk_datapoints doesn't exist
```

**Solution:** Storage auto-creates tables on first use, but may fail if permissions insufficient.

```sql
-- Create manually if needed
CREATE TABLE IF NOT EXISTS dtk_datapoints (
    id UInt64,
    metric_name String,
    collected_at DateTime64(3),
    value Nullable(Float64),
    is_missing UInt8,
    context String,
    inserted_at DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
PARTITION BY toYYYYMM(collected_at)
ORDER BY (metric_name, collected_at, id);
```

#### 2. Permissions Issue

**Error:**
```
Not enough privileges to insert
```

**Solution:**
```sql
-- Grant insert permissions
GRANT INSERT, CREATE TABLE ON database.* TO user;
```

#### 3. Disk Space

**Error:**
```
No space left on device
```

**Solution:**
```bash
# Check disk space
df -h

# Clean up old data
SELECT
    metric_name,
    count() as points,
    formatReadableSize(sum(bytes_on_disk)) as disk_usage
FROM system.parts
WHERE table = 'dtk_datapoints'
GROUP BY metric_name
ORDER BY disk_usage DESC;

# Delete old partitions
ALTER TABLE dtk_datapoints DROP PARTITION '202401';
```

---

### Slow Query Performance

**Symptoms:**
- `query_datapoints()` takes >5 seconds
- Detection runs slowly

**Solutions:**

1. **Check indexes:**
```sql
-- Should have ORDER BY (metric_name, collected_at)
SHOW CREATE TABLE dtk_datapoints;
```

2. **Add partition pruning:**
```sql
-- Query uses partition pruning automatically
-- But ensure partitions exist:
SELECT
    partition,
    rows,
    formatReadableSize(bytes_on_disk) as size
FROM system.parts
WHERE table = 'dtk_datapoints'
ORDER BY partition DESC;
```

3. **Optimize window size:**
```yaml
# ❌ Slow (loading 90 days for every check)
detector:
  params:
    window_size: "90 days"

# ✅ Faster (30 days usually sufficient)
detector:
  params:
    window_size: "30 days"
```

4. **Run OPTIMIZE:**
```sql
-- Merge parts for better performance
OPTIMIZE TABLE dtk_datapoints FINAL;
```

---

## Performance Issues

### Slow Historical Data Loading

**Symptoms:**
- Loading 30 days takes hours
- High memory usage

**Solutions:**

1. **Use batch loading:**
```yaml
# DetectK automatically batches by default
schedule:
  batch_load_days: 30  # Load 30 days at a time (default)
```

2. **Optimize source query:**
```sql
-- ❌ Slow (scans full table)
SELECT count() as value
FROM huge_table
WHERE timestamp >= '{{ period_start }}'

-- ✅ Fast (uses partition pruning)
SELECT count() as value
FROM huge_table
WHERE toDate(timestamp) >= toDate('{{ period_start }}')  -- Helps pruning
  AND timestamp >= toDateTime('{{ period_start }}')
```

3. **Add index to source table:**
```sql
-- For ClickHouse
ALTER TABLE events ADD INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 4;

-- For PostgreSQL
CREATE INDEX idx_events_timestamp ON events(timestamp);
```

4. **Reduce interval granularity during load:**
```yaml
# Load hourly instead of 10-minute for historical data
schedule:
  interval: "1 hour"  # Temporarily

# After loading, switch back to:
schedule:
  interval: "10 minutes"
```

---

### High Memory Usage

**Symptoms:**
```
MemoryError: Out of memory
```

**Causes:**
- Loading too much data at once
- Large seasonal groups

**Solutions:**

1. **Reduce batch size:**
```yaml
schedule:
  batch_load_days: 7  # Instead of 30
```

2. **Reduce window size:**
```yaml
detector:
  params:
    window_size: "14 days"  # Instead of 90 days
```

3. **Use separate seasonality (smaller groups):**
```yaml
detector:
  params:
    use_combined_seasonality: false  # OR mode
```

---

## Debugging Tips

### Enable Verbose Logging

```bash
# CLI
dtk run configs/my_metric.yaml --verbose

# Python API
import logging
logging.basicConfig(level=logging.DEBUG)
```

Output shows:
- Rendered queries
- Query execution times
- Data points collected
- Detection results
- Alert decisions

---

### Test Components Individually

```python
# Test collector
from detectk.check import MetricCheck
from datetime import datetime, timedelta

checker = MetricCheck()
config = checker._load_config("configs/sessions.yaml")

# Render query manually
from jinja2 import Template
template = Template(config.collector.params["query"])
rendered = template.render(
    period_start=(datetime.now() - timedelta(minutes=10)).isoformat(),
    period_finish=datetime.now().isoformat(),
    interval="10 minutes",
)
print(rendered)

# Test in database directly
# clickhouse-client --query "<rendered query>"
```

---

### Check Storage Directly

```sql
-- ClickHouse: Check collected data
SELECT
    metric_name,
    count() as points,
    min(collected_at) as earliest,
    max(collected_at) as latest,
    avg(value) as avg_value,
    quantile(0.5)(value) as median
FROM dtk_datapoints
WHERE metric_name = 'sessions_10min'
GROUP BY metric_name;

-- Check detection results
SELECT
    metric_name,
    detected_at,
    value,
    is_anomaly,
    anomaly_score,
    lower_bound,
    upper_bound,
    alert_sent
FROM dtk_detections
WHERE metric_name = 'sessions_10min'
ORDER BY detected_at DESC
LIMIT 20;
```

---

### Validate Configuration

```bash
# Use dtk validate
dtk validate configs/my_metric.yaml

# Or Python
from detectk.config import ConfigLoader
loader = ConfigLoader()
config = loader.load("configs/my_metric.yaml")
print(config.model_dump_json(indent=2))
```

---

### Test Alert Webhook

```bash
# Mattermost
curl -X POST "${MATTERMOST_WEBHOOK}" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Test alert from DetectK",
    "username": "DetectK Test"
  }'

# Slack
curl -X POST "${SLACK_WEBHOOK}" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Test alert from DetectK"
  }'
```

---

## Getting Help

If you're still stuck:

1. **Check documentation:**
   - [QUICKSTART.md](QUICKSTART.md) - Getting started guide
   - [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
   - [examples/](examples/) - 33 working configurations
   - [examples/seasonal/README.md](examples/seasonal/README.md) - Seasonality guide

2. **Search examples:**
```bash
# Find similar configs
grep -r "threshold" examples/
grep -r "seasonal_features" examples/
```

3. **Enable verbose logging:**
```bash
dtk run configs/my_metric.yaml --verbose 2>&1 | tee debug.log
```

4. **Open GitHub issue:**
   - https://github.com/alexeiveselov92/detectk/issues
   - Include: config file, error message, verbose logs

---

## Common Patterns

### Pattern: Test New Metric

```bash
# 1. Validate config
dtk validate configs/new_metric.yaml

# 2. Test query manually in database
clickhouse-client --query "..."

# 3. Run once with verbose logging
dtk run configs/new_metric.yaml --verbose

# 4. Load historical data
# (set schedule.start_time, alerter.enabled=false)
dtk run configs/new_metric.yaml

# 5. Enable production monitoring
# (remove schedule.start_time, alerter.enabled=true)
```

---

### Pattern: Debug False Positives

```bash
# 1. Check detection results
clickhouse-client --query "
  SELECT
      detected_at,
      value,
      lower_bound,
      upper_bound,
      anomaly_score
  FROM dtk_detections
  WHERE metric_name = 'sessions_10min'
    AND is_anomaly = 1
  ORDER BY detected_at DESC
  LIMIT 20
"

# 2. Compare with historical data
clickhouse-client --query "
  SELECT
      quantile(0.5)(value) as median,
      quantile(0.25)(value) as q25,
      quantile(0.75)(value) as q75,
      min(value) as min_val,
      max(value) as max_val
  FROM dtk_datapoints
  WHERE metric_name = 'sessions_10min'
"

# 3. Adjust n_sigma in config
# detector.params.n_sigma: 3.0 → 3.5 → 4.0

# 4. Test again
dtk run configs/sessions_10min.yaml --verbose
```

---

**Remember:** Most issues are configuration-related. Always start with `dtk validate` and `--verbose` logging!
