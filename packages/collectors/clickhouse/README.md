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
        count() as value,
        now() as timestamp
      FROM sessions
      WHERE timestamp > now() - INTERVAL 10 MINUTE

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
    detected_at DateTime64(3),
    value Float64,
    is_anomaly UInt8,
    anomaly_score Nullable(Float64),
    lower_bound Nullable(Float64),
    upper_bound Nullable(Float64),
    ...
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(detected_at)
ORDER BY (metric_name, detected_at);
```

Tables are created automatically on first use.

## License

MIT
