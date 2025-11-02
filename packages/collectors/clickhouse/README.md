# detectk-collectors-clickhouse

ClickHouse collector and storage for DetectK.

## Installation

```bash
pip install detectk-collectors-clickhouse
```

## Features

- **ClickHouseCollector**: Collect metrics from ClickHouse queries
- **ClickHouseStorage**: Store metric history in ClickHouse (`dtk_datapoints` and `dtk_detections` tables)
- Auto-registration in DetectK registries
- Connection pooling and error handling
- Partitioned tables for performance

## Usage

### As Collector

```yaml
# config.yaml
name: "sessions_10min"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    database: "analytics"
    query: |
      SELECT
        toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
        count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detector:
  type: "threshold"
  params:
    threshold: 1000

alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
```

### As Storage

```yaml
# config.yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    database: "default"
    save_detections: false  # Optional: save detection results
```

### Multiple Detectors (A/B Testing)

```yaml
# config.yaml - Compare multiple detection strategies
name: "sessions_10min"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    database: "analytics"
    query: |
      SELECT
        toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
        count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

# Multiple detectors with auto-generated IDs
detectors:
  - type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 3.0
    # ID auto-generated: e.g., "a1b2c3d4"

  - type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 5.0
    # ID auto-generated: e.g., "b2c3d4e5" (different from above)

  - id: "zscore_7d"  # Manual ID override
    type: "zscore"
    params:
      window_size: "7 days"

alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"

storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    database: "default"
    save_detections: true  # Save all detector results for comparison
```

**How it works:**
- Each detector gets a unique ID (auto-generated 8-char hash or manual)
- All detector results are saved to `dtk_detections` with their `detector_id`
- Alert sent if ANY detector finds anomaly (configurable in future)
- Query results: `SELECT * FROM dtk_detections WHERE metric_name = 'sessions_10min' ORDER BY detected_at, detector_id`

## Configuration

### Collector Parameters

- `host`: ClickHouse server host (default: localhost)
- `port`: ClickHouse server port (default: 9000)
- `database`: Database name (default: default)
- `user`: Username (optional)
- `password`: Password (optional)
- `query`: SQL query returning `value` and optionally `timestamp` columns
- `timeout`: Query timeout in seconds (default: 30)
- `secure`: Use SSL connection (default: false)

### Storage Parameters

- `host`: ClickHouse server host (default: localhost)
- `port`: ClickHouse server port (default: 9000)
- `database`: Database name (default: default)
- `user`: Username (optional)
- `password`: Password (optional)
- `timeout`: Query timeout in seconds (default: 30)
- `secure`: Use SSL connection (default: false)
- `save_detections`: Save detection results to `dtk_detections` table (default: false)

## Storage Schema

### dtk_datapoints

Collected metric values (required for detection):

```sql
CREATE TABLE dtk_datapoints (
    id UInt64,
    metric_name String,
    collected_at DateTime64(3),
    value Float64,
    context String  -- JSON string
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(collected_at)
ORDER BY (metric_name, collected_at);
```

### dtk_detections

Detection results (optional, for audit/cooldown):

```sql
CREATE TABLE dtk_detections (
    id UInt64,
    metric_name String,
    detector_id String,  -- Unique detector identifier (for multi-detector support)
    detected_at DateTime64(3),
    value Float64,
    is_anomaly UInt8,
    anomaly_score Nullable(Float64),
    lower_bound Nullable(Float64),
    upper_bound Nullable(Float64),
    direction Nullable(String),
    percent_deviation Nullable(Float64),
    detector_type String,
    detector_params String,  -- JSON with full params for transparency
    alert_sent UInt8,
    alert_reason Nullable(String),
    alerter_type Nullable(String),
    context String  -- JSON
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(detected_at)
ORDER BY (metric_name, detector_id, detected_at);
```

**Multi-Detector Support**: The `detector_id` field allows storing results from multiple detectors for the same metric. Each detector gets a unique ID (auto-generated or manual), enabling A/B testing and parameter tuning.

Tables are created automatically on first use.

## License

MIT
