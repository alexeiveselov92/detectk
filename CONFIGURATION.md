# DetectK Configuration Reference

Complete reference for all configuration options in DetectK.

---

## Table of Contents

1. [Configuration File Structure](#configuration-file-structure)
2. [Top-Level Fields](#top-level-fields)
3. [Collector Configuration](#collector-configuration)
4. [Storage Configuration](#storage-configuration)
5. [Detector Configuration](#detector-configuration)
6. [Alerter Configuration](#alerter-configuration)
7. [Schedule Configuration](#schedule-configuration)
8. [Environment Variables](#environment-variables)
9. [Jinja2 Templates](#jinja2-templates)
10. [Connection Profiles](#connection-profiles)
11. [Examples](#examples)

---

## Configuration File Structure

DetectK uses YAML for configuration. Each metric is defined in a separate file:

```yaml
# Basic structure
name: "metric_name"
description: "What this metric monitors"
tags: ["tag1", "tag2"]  # Optional

collector:
  type: "collector_type"
  params: { ... }

storage:
  enabled: true
  type: "storage_type"
  params: { ... }

detector:
  type: "detector_type"
  params: { ... }

# OR multiple detectors
detectors:
  - type: "mad"
    params: { ... }
  - type: "threshold"
    params: { ... }

alerter:
  enabled: true
  type: "alerter_type"
  params: { ... }

schedule:
  interval: "10 minutes"
```

---

## Top-Level Fields

### `name` (required)

Unique identifier for the metric.

**Type:** `string`
**Format:** Alphanumeric, underscores, hyphens
**Example:** `"sessions_10min"`, `"revenue_hourly"`

```yaml
name: "api_errors_5min"
```

### `description` (required)

Human-readable description of what the metric monitors.

**Type:** `string`
**Example:**

```yaml
description: "Monitor API error rate every 5 minutes"
```

### `tags` (optional)

Tags for grouping and filtering metrics.

**Type:** `list[string]`
**Default:** `[]`
**Use Cases:**
- Group by priority: `["critical", "important"]`
- Group by interval: `["hourly", "daily"]`
- Group by domain: `["revenue", "api", "product"]`

**Example:**

```yaml
tags:
  - "critical"
  - "api"
  - "realtime"
```

**CLI Usage:**
```bash
# Run all critical metrics
dtk run-tagged --tags critical

# Run hourly AND critical (AND logic)
dtk run-tagged --tags hourly --tags critical --match-all
```

---

## Collector Configuration

Defines how to collect metric data from source.

### Structure

```yaml
collector:
  profile: "profile_name"  # Optional: use connection profile
  type: "collector_type"    # Required if no profile
  params:
    # Collector-specific parameters
```

### Common Parameters

#### Query Template (required for all SQL collectors)

**CRITICAL:** Query must return TIME SERIES (multiple rows), not single value!

**Type:** `string` (multi-line YAML)
**Required Variables:**
- `{{ period_start }}` - Start of time range (ISO format)
- `{{ period_finish }}` - End of time range (ISO format)
- `{{ interval }}` - Time interval (e.g., "10 minutes")

**Example:**

```yaml
collector:
  params:
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        count() AS value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time
```

#### Column Mapping (required)

Tell DetectK which columns contain timestamp and value:

```yaml
collector:
  params:
    timestamp_column: "period_time"  # Column with timestamp
    value_column: "value"            # Column with metric value
    context_columns: ["hour_of_day", "day_of_week"]  # Optional: seasonal features
```

### ClickHouse Collector

**Type:** `clickhouse`
**Package:** `detectk-collectors-clickhouse`

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `host` | `string` | Yes* | `localhost` | ClickHouse server host |
| `port` | `int` | No | `9000` | ClickHouse native protocol port |
| `database` | `string` | Yes* | `default` | Database name |
| `user` | `string` | No | `default` | Username |
| `password` | `string` | No | `""` | Password |
| `query` | `string` | Yes | - | SQL query template |
| `timestamp_column` | `string` | Yes | - | Timestamp column name |
| `value_column` | `string` | Yes | - | Value column name |
| `context_columns` | `list[string]` | No | `[]` | Seasonal feature columns |
| `secure` | `bool` | No | `false` | Use TLS |
| `verify` | `bool` | No | `true` | Verify SSL certificate |

*Can be provided via environment variables

#### Example

```yaml
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    port: 9000
    database: "analytics"
    user: "readonly"
    password: "${CLICKHOUSE_PASSWORD}"

    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        uniqExact(user_id) AS value,
        toHour(period_time) AS hour_of_day,
        toDayOfWeek(period_time) AS day_of_week
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"
    context_columns: ["hour_of_day", "day_of_week"]
```

### SQL Collector (PostgreSQL, MySQL, SQLite)

**Type:** `sql`
**Package:** `detectk-collectors-sql`

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `dialect` | `string` | Yes | - | `postgresql`, `mysql`, or `sqlite` |
| `connection_string` | `string` | Yes* | - | SQLAlchemy connection string |
| `host` | `string` | Yes* | - | Database host |
| `port` | `int` | No | varies | Database port |
| `database` | `string` | Yes* | - | Database name |
| `user` | `string` | Yes* | - | Username |
| `password` | `string` | Yes* | - | Password |
| `query` | `string` | Yes | - | SQL query template |
| `timestamp_column` | `string` | Yes | - | Timestamp column name |
| `value_column` | `string` | Yes | - | Value column name |

*Either `connection_string` OR individual params required

#### PostgreSQL Example

```yaml
collector:
  type: "sql"
  params:
    dialect: "postgresql"
    host: "postgres.example.com"
    port: 5432
    database: "analytics"
    user: "readonly"
    password: "${POSTGRES_PASSWORD}"

    query: |
      SELECT
        date_trunc('hour', timestamp) AS period_time,
        COUNT(DISTINCT user_id) AS value
      FROM sessions
      WHERE timestamp >= '{{ period_start }}'::timestamp
        AND timestamp < '{{ period_finish }}'::timestamp
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"
```

#### MySQL Example

```yaml
collector:
  type: "sql"
  params:
    dialect: "mysql"
    connection_string: "mysql+pymysql://user:pass@localhost/analytics"

    query: |
      SELECT
        DATE_FORMAT(timestamp, '%Y-%m-%d %H:00:00') AS period_time,
        COUNT(*) AS value
      FROM orders
      WHERE timestamp >= '{{ period_start }}'
        AND timestamp < '{{ period_finish }}'
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"
```

#### SQLite Example

```yaml
collector:
  type: "sql"
  params:
    dialect: "sqlite"
    database: "/path/to/database.db"

    query: |
      SELECT
        strftime('%Y-%m-%d %H:00:00', timestamp) AS period_time,
        COUNT(*) AS value
      FROM events
      WHERE timestamp >= datetime('{{ period_start }}')
        AND timestamp < datetime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"
```

### HTTP Collector

**Type:** `http`
**Package:** `detectk-collectors-http`

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | `string` | Yes | API endpoint URL |
| `method` | `string` | No | HTTP method (default: `GET`) |
| `headers` | `dict` | No | HTTP headers |
| `params` | `dict` | No | Query parameters |
| `data_path` | `string` | Yes | JSON path to metric value |
| `timestamp_path` | `string` | No | JSON path to timestamp |

#### Example (Prometheus)

```yaml
collector:
  type: "http"
  params:
    url: "http://prometheus:9090/api/v1/query"
    params:
      query: "up{job='my-api'}"
    data_path: "data.result[0].value[1]"
    timestamp_path: "data.result[0].value[0]"
```

---

## Storage Configuration

Defines where to store collected datapoints for historical analysis.

### Structure

```yaml
storage:
  enabled: true  # Required
  type: "storage_type"
  params:
    # Storage-specific parameters

  # Retention policies
  datapoints_retention_days: 90
  detections_retention_days: 30

  # Optional: save detection results
  save_detections: false
```

### ClickHouse Storage

**Type:** `clickhouse`

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `host` | `string` | Yes* | - | ClickHouse host |
| `port` | `int` | No | `9000` | Port |
| `database` | `string` | Yes* | - | Database name |
| `user` | `string` | No | `default` | Username |
| `password` | `string` | No | `""` | Password |
| `datapoints_retention_days` | `int` | No | `90` | Keep datapoints for N days |
| `detections_retention_days` | `int` | No | `30` | Keep detection results for N days |
| `save_detections` | `bool` | No | `false` | Save detection results |

*Can use connection profile

#### Example

```yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "${METRICS_DB_HOST}"
    database: "metrics"
    user: "detectk"
    password: "${METRICS_DB_PASSWORD}"

  datapoints_retention_days: 90
  save_detections: false  # Don't save detection results (save space)
```

---

## Detector Configuration

Defines how to detect anomalies in collected data.

### Single Detector

```yaml
detector:
  type: "detector_type"
  params:
    # Detector-specific parameters
```

### Multiple Detectors (A/B Testing)

```yaml
detectors:
  - id: "conservative"  # Optional: custom ID
    type: "mad"
    params:
      n_sigma: 5.0

  - type: "mad"  # Auto-generated ID
    params:
      n_sigma: 3.0

  - type: "threshold"
    params:
      threshold: 1000
```

**Alert Behavior:** Alert sent if ANY detector finds anomaly.

### Threshold Detector

**Type:** `threshold`

Simple threshold-based detection.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operator` | `string` | Yes | `greater_than`, `less_than`, `equals`, `between`, `outside` |
| `threshold` | `float` | Yes* | Threshold value |
| `min_value` | `float` | Yes** | Minimum for `between`/`outside` |
| `max_value` | `float` | Yes** | Maximum for `between`/`outside` |

*Required for `greater_than`, `less_than`, `equals`
**Required for `between`, `outside`

#### Examples

```yaml
# Simple threshold
detector:
  type: "threshold"
  params:
    operator: "less_than"
    threshold: 1000  # Alert if value < 1000

# Range check
detector:
  type: "threshold"
  params:
    operator: "between"
    min_value: 100
    max_value: 1000  # Alert if 100 <= value <= 1000
```

### MAD Detector (Median Absolute Deviation)

**Type:** `mad`

Robust statistical anomaly detection using MAD.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `window_size` | `string` | Yes | - | Historical window (e.g., "30 days") |
| `n_sigma` | `float` | No | `3.0` | Sensitivity (2.5=more, 4.0=less) |
| `seasonal_features` | `list[string]` | No | `[]` | Seasonal grouping columns |
| `use_combined_seasonality` | `bool` | No | `false` | Combine features (AND logic) |
| `use_weighted` | `bool` | No | `false` | Use exponential weights |
| `weights_type` | `string` | No | `exponential` | Weight type |

#### Examples

```yaml
# Basic MAD
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

# With seasonality (separate)
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features: ["hour_of_day", "day_of_week"]
    use_combined_seasonality: false  # Compare separately

# Combined seasonality (strict)
detector:
  type: "mad"
  params:
    window_size: "30 days"
    seasonal_features: ["hour_of_day", "day_of_week"]
    use_combined_seasonality: true  # Monday 9AM vs Monday 9AM only
```

### Z-Score Detector

**Type:** `zscore`

Standard deviation-based detection.

#### Parameters

Same as MAD detector, but uses mean/stddev instead of median/MAD.

```yaml
detector:
  type: "zscore"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features: ["hour_of_day"]
```

### Missing Data Detector

**Type:** `missing_data`

Detects when data is missing or stale.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `max_staleness_minutes` | `int` | Yes | Alert if no data for N minutes |

```yaml
detector:
  type: "missing_data"
  params:
    max_staleness_minutes: 10  # Alert if no data for 10 min
```

---

## Alerter Configuration

Defines how to send alerts when anomalies are detected.

### Structure

```yaml
alerter:
  enabled: true  # Set false for historical loads
  profile: "profile_name"  # Optional: use connection profile
  type: "alerter_type"
  params:
    # Alerter-specific parameters
```

### Mattermost Alerter

**Type:** `mattermost`
**Package:** `detectk-alerters-mattermost`

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `webhook_url` | `string` | Yes | Mattermost webhook URL |
| `channel` | `string` | No | Override channel |
| `username` | `string` | No | Bot username |
| `icon_emoji` | `string` | No | Bot icon |
| `cooldown_minutes` | `int` | No | Minimum time between alerts (default: 60) |
| `template` | `string` | No | Custom Jinja2 template |

#### Example

```yaml
alerter:
  enabled: true
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    channel: "#ops-alerts"
    username: "DetectK Bot"
    icon_emoji: ":chart_with_upwards_trend:"
    cooldown_minutes: 60
```

### Slack Alerter

**Type:** `slack`
**Package:** `detectk-alerters-slack`

#### Parameters

Same as Mattermost, uses Slack Block Kit for formatting.

```yaml
alerter:
  enabled: true
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    channel: "#monitoring"
    cooldown_minutes: 30
```

---

## Schedule Configuration

Defines when and how often to run the metric check.

### Structure

```yaml
schedule:
  interval: "10 minutes"  # Required

  # Optional: historical load
  start_time: "2024-01-01"
  end_time: "2024-03-01"
  batch_load_days: 30
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `interval` | `string` | Yes | Check interval (e.g., "10 minutes", "1 hour") |
| `start_time` | `string` | No | Start loading from this time (ISO format) |
| `end_time` | `string` | No | Load until this time |
| `batch_load_days` | `int` | No | Days per batch (default: 30) |

### Examples

#### Continuous Monitoring

```yaml
schedule:
  interval: "10 minutes"
```

#### Historical Data Load

```yaml
schedule:
  interval: "10 minutes"
  start_time: "2024-01-01"
  end_time: "2024-03-01"
  batch_load_days: 30

alerter:
  enabled: false  # Don't spam during historical load
```

---

## Environment Variables

### Substitution Syntax

Use `${VAR_NAME}` or `${VAR_NAME:-default}` in configs:

```yaml
collector:
  params:
    host: "${CLICKHOUSE_HOST}"  # Required
    port: "${CLICKHOUSE_PORT:-9000}"  # Optional with default
    password: "${CLICKHOUSE_PASSWORD}"
```

### Standard Environment Variables

ClickHouse:
- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`

PostgreSQL:
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DATABASE`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Alerters:
- `MATTERMOST_WEBHOOK`
- `SLACK_WEBHOOK`

---

## Jinja2 Templates

### Template Variables

Available in collector queries:

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `{{ period_start }}` | `string` | Start of time range | `2024-11-01 10:00:00` |
| `{{ period_finish }}` | `string` | End of time range | `2024-11-01 10:10:00` |
| `{{ interval }}` | `string` | Time interval | `10 minutes` |
| `{{ execution_time }}` | `string` | When check ran | `2024-11-01 10:10:00` |

### Custom Filters

| Filter | Description | Example |
|--------|-------------|---------|
| `datetime_format(fmt)` | Format datetime | `{{ period_start \| datetime_format('%Y-%m-%d') }}` |

### Example

```yaml
collector:
  params:
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        count() AS value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
        AND date = '{{ period_start | datetime_format('%Y-%m-%d') }}'
      GROUP BY period_time
```

---

## Connection Profiles

Store credentials separately from configs.

### Profile File

Create `detectk_profiles.yaml` (gitignored):

```yaml
profiles:
  clickhouse_prod:
    type: "clickhouse"
    params:
      host: "prod.clickhouse.com"
      port: 9000
      database: "analytics"
      user: "readonly"
      password: "secret123"

  mattermost_ops:
    type: "mattermost"
    params:
      webhook_url: "https://mattermost.com/hooks/xxx"
      channel: "#ops-alerts"
```

### Use in Config

```yaml
collector:
  profile: "clickhouse_prod"
  params:
    query: |
      SELECT ...

alerter:
  profile: "mattermost_ops"
```

**Lookup Order:**
1. `./detectk_profiles.yaml` (local, highest priority)
2. `~/.detectk/profiles.yaml` (global)

---

## Complete Example

```yaml
name: "sessions_10min"
description: "Monitor user sessions every 10 minutes with seasonality"

tags:
  - "critical"
  - "product"
  - "realtime"

collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    database: "analytics"
    password: "${CLICKHOUSE_PASSWORD}"

    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        uniqExact(user_id) AS value,
        toHour(period_time) AS hour_of_day,
        toDayOfWeek(period_time) AS day_of_week
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"
    context_columns: ["hour_of_day", "day_of_week"]

storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "${METRICS_DB_HOST}"
    database: "metrics"
  datapoints_retention_days: 90
  save_detections: false

detectors:
  - type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 3.0
      seasonal_features: ["hour_of_day", "day_of_week"]
      use_combined_seasonality: true

  - type: "threshold"
    params:
      operator: "less_than"
      threshold: 100

alerter:
  enabled: true
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    channel: "#product-alerts"
    cooldown_minutes: 60

schedule:
  interval: "10 minutes"
```

---

## Validation

Validate config before running:

```bash
dtk validate my_metric.yaml
```

Common validation errors:
- Missing required fields
- Invalid detector type
- Query missing `{{ period_start }}`
- Invalid interval format

---

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [examples/](examples/) - Working configurations
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment

