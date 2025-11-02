# Collectors Guide

Collectors fetch metric data from various sources. This guide covers all available collectors and how to use them.

## Available Collectors

| Collector | Package | Data Sources |
|-----------|---------|--------------|
| ClickHouse | `detectk-collectors-clickhouse` | ClickHouse databases |
| SQL | `detectk-collectors-sql` | PostgreSQL, MySQL, SQLite |
| HTTP | `detectk-collectors-http` | REST APIs |

## ClickHouse Collector

### Installation

```bash
pip install detectk-collectors-clickhouse
```

### Basic Usage

```yaml
collector:
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
    user: "default"
    password: ""

    query: |
      SELECT count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

### Connection Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `host` | string | Yes | - | ClickHouse server host |
| `port` | int | No | 9000 | Native protocol port |
| `database` | string | Yes | - | Database name |
| `user` | string | No | "default" | Username |
| `password` | string | No | "" | Password |
| `secure` | bool | No | false | Use TLS connection |
| `query` | string | Yes | - | SQL query returning `value` column |

### Query Requirements

**Query MUST return a column named `value`:**

```sql
-- ✓ GOOD
SELECT count() as value FROM events

-- ✓ GOOD
SELECT avg(duration) as value FROM requests

-- ✗ BAD - missing 'as value'
SELECT count() FROM events
```

### Query Templates

Use Jinja2 templates for dynamic queries:

```yaml
collector:
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"

    query: |
      SELECT count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}') 10 MINUTE
        AND timestamp < '{{ execution_time }}'
```

**Available template variables:**
- `{{ execution_time }}` - Current check time (datetime)
- `{{ metric_name }}` - Metric name from config

**Custom variables:**

```yaml
collector:
  params:
    query: |
      SELECT
        toStartOfDay(toDateTime('{{ period_finish }}')) as period_time,
        count() as value
      FROM {{ table_name }}
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

    query_variables:
      table_name: "events"
```

### Time Window Queries

**Last 10 minutes:**
```sql
SELECT count() as value
FROM events
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**Specific time range (for backtesting):**
```sql
SELECT count() as value
FROM events
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}') 10 MINUTE
  AND timestamp < '{{ execution_time }}'
```

**Aggregated by time:**
```sql
SELECT count() as value
FROM events
WHERE toStartOfInterval(timestamp, INTERVAL 10 MINUTE) =
      toStartOfInterval('{{ execution_time }}', INTERVAL 10 MINUTE)
```

### Complex Metrics

**Average duration:**
```sql
SELECT avg(duration_ms) as value
FROM requests
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**Error rate:**
```sql
SELECT
    countIf(status_code >= 400) / count() * 100 as value
FROM http_requests
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**95th percentile:**
```sql
SELECT quantile(0.95)(response_time) as value
FROM api_calls
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**Revenue per user:**
```sql
SELECT
    sum(amount) / countDistinct(user_id) as value
FROM purchases
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

### Using Connection Profiles

**Recommended approach:**

Create `detectk_profiles.yaml`:
```yaml
profiles:
  prod_clickhouse:
    type: "clickhouse"
    host: "prod.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${CLICKHOUSE_PASSWORD}"
```

Use in metric config:
```yaml
collector:
  profile: "prod_clickhouse"
  params:
    query: |
      SELECT
        toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
        count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

See [Connection Profiles Guide](profiles.md) for details.

### Handling Empty Results

If query returns no rows, collector returns `value=0.0`:

```python
DataPoint(
    timestamp=execution_time,
    value=0.0,
    metadata={"is_empty_result": True}
)
```

**Best practice - always return a row:**

```sql
-- ✓ GOOD - always returns 1 row
SELECT count() as value FROM events

-- ✗ BAD - might return 0 rows
SELECT value FROM metrics WHERE id = 123
```

**Track data freshness:**

```sql
SELECT
    count() as value,
    max(timestamp) as last_event_time
FROM events
```

### Connection Pooling

ClickHouse collector uses connection pooling internally. Configure via environment:

```bash
export CLICKHOUSE_POOL_SIZE=10
export CLICKHOUSE_POOL_TIMEOUT=30
```

## SQL Collector (PostgreSQL, MySQL, SQLite)

### Installation

```bash
pip install detectk-collectors-sql
```

### PostgreSQL

```yaml
collector:
  type: "sql"
  params:
    connection_string: "postgresql://user:password@localhost:5432/dbname"

    query: |
      SELECT
        date_trunc('minute', '{{ period_finish }}'::timestamp) as period_time,
        COUNT(*) as value
      FROM events
      WHERE created_at >= '{{ period_start }}'::timestamp
        AND created_at < '{{ period_finish }}'::timestamp
```

### MySQL

```yaml
collector:
  type: "sql"
  params:
    connection_string: "mysql+pymysql://user:password@localhost:3306/dbname"

    query: |
      SELECT
        DATE_ADD('{{ period_start }}', INTERVAL 10 MINUTE) as period_time,
        COUNT(*) as value
      FROM events
      WHERE created_at >= '{{ period_start }}'
        AND created_at < '{{ period_finish }}'
```

### SQLite

```yaml
collector:
  type: "sql"
  params:
    connection_string: "sqlite:///path/to/database.db"

    query: |
      SELECT
        datetime('{{ period_start }}', '+10 minutes') as period_time,
        COUNT(*) as value
      FROM events
      WHERE created_at >= datetime('{{ period_start }}')
        AND created_at < datetime('{{ period_finish }}')
```

### Using Profiles

```yaml
profiles:
  postgres_prod:
    type: "sql"
    connection_string: "${POSTGRES_DSN}"
```

## HTTP Collector (REST APIs)

### Installation

```bash
pip install detectk-collectors-http
```

### Basic Usage

```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/metrics/sessions"
    method: "GET"

    # Extract value from JSON response
    value_path: "data.sessions.count"
```

### Authentication

**Bearer Token:**
```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/metrics"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
    value_path: "metrics.value"
```

**API Key:**
```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/metrics"
    headers:
      X-API-Key: "${API_KEY}"
    value_path: "result.count"
```

**Basic Auth:**
```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/metrics"
    auth:
      username: "${API_USER}"
      password: "${API_PASSWORD}"
    value_path: "data.value"
```

### POST Requests

```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/query"
    method: "POST"
    headers:
      Content-Type: "application/json"
    body: |
      {
        "query": "SELECT count() FROM events",
        "format": "json"
      }
    value_path: "data[0].count"
```

### Value Extraction

**JSON path notation:**

```yaml
# Response: {"data": {"metrics": {"sessions": 1234}}}
value_path: "data.metrics.sessions"

# Response: {"results": [{"value": 1234}]}
value_path: "results[0].value"

# Response: {"count": 1234}
value_path: "count"
```

## Best Practices

### 1. Always Return a Value

```sql
-- ✓ GOOD
SELECT COALESCE(count(), 0) as value FROM events

-- ✗ BAD - might fail if no rows
SELECT value FROM single_row_table WHERE id = 1
```

### 2. Use Time Windows

```sql
-- ✓ GOOD - explicit time range
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

-- ✗ BAD - unbounded query
WHERE status = 'active'
```

### 3. Use Indexes

Ensure your queries use indexes:

```sql
-- ClickHouse
ALTER TABLE events ADD INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 4;

-- PostgreSQL
CREATE INDEX idx_events_created_at ON events(created_at);
```

### 4. Test Query Performance

```bash
# ClickHouse
EXPLAIN SYNTAX SELECT count() as value FROM events WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}');

# PostgreSQL
EXPLAIN ANALYZE SELECT COUNT(*) as value FROM events WHERE created_at >= NOW() - INTERVAL '10 minutes';
```

### 5. Use Connection Profiles

Don't hardcode credentials in metric configs. Use `detectk_profiles.yaml`.

### 6. Handle Timezones

```sql
-- ClickHouse - use server timezone
SELECT count() as value
FROM events
WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

-- PostgreSQL - explicit timezone
SELECT COUNT(*) as value
FROM events
WHERE created_at AT TIME ZONE 'UTC' >= NOW() AT TIME ZONE 'UTC' - INTERVAL '10 minutes'
```

## Troubleshooting

### "No column named 'value' in query result"

Query must return a column named `value`:

```sql
-- ✗ Wrong
SELECT count() FROM events

-- ✓ Correct
SELECT count() as value FROM events
```

### "Connection refused"

Check host/port and firewall:

```bash
# Test ClickHouse connection
clickhouse-client --host localhost --port 9000

# Test PostgreSQL connection
psql "postgresql://user@localhost:5432/dbname"
```

### "Query timeout"

Optimize query or increase timeout:

```yaml
collector:
  params:
    query_timeout: 60  # seconds
```

### Empty results

Query returns no rows. Use `count()` or `COALESCE`:

```sql
SELECT COALESCE(avg(value), 0) as value FROM metrics
```

## Next Steps

- **[Detectors Guide](detectors.md)** - Process collected data
- **[Connection Profiles](profiles.md)** - Secure credential management
- **[Configuration Reference](configuration.md)** - Complete schema
