# DetectK SQL Collectors

Generic SQL collector for DetectK with support for PostgreSQL, MySQL, and SQLite.

## Installation

```bash
# Core package (supports SQLite out of the box)
pip install detectk-collectors-sql

# With PostgreSQL support
pip install detectk-collectors-sql[postgres]

# With MySQL support
pip install detectk-collectors-sql[mysql]

# With all database drivers
pip install detectk-collectors-sql[all]
```

## Supported Databases

- **PostgreSQL** (9.6+)
- **MySQL** (5.7+, 8.0+)
- **SQLite** (3.x)

## Usage

### PostgreSQL

```yaml
name: "user_sessions_postgres"
description: "Monitor active sessions in PostgreSQL"

collector:
  type: "sql"
  params:
    connection_string: "postgresql://user:password@localhost:5432/analytics"
    query: |
      SELECT
        date_trunc('minute', '{{ period_finish }}'::timestamp) as period_time,
        COUNT(DISTINCT user_id) as value
      FROM sessions
      WHERE created_at >= '{{ period_start }}'::timestamp
        AND created_at < '{{ period_finish }}'::timestamp

detector:
  type: "threshold"
  params:
    threshold: 100
    operator: "less_than"
```

### MySQL

```yaml
name: "orders_mysql"
description: "Monitor order volume in MySQL"

collector:
  type: "sql"
  params:
    connection_string: "mysql://user:password@localhost:3306/ecommerce"
    query: |
      SELECT
        DATE_ADD('{{ period_start }}', INTERVAL 1 HOUR) as period_time,
        COUNT(*) as value
      FROM orders
      WHERE created_at >= '{{ period_start }}'
        AND created_at < '{{ period_finish }}'
```

### SQLite

```yaml
name: "local_metrics_sqlite"
description: "Monitor local database metrics"

collector:
  type: "sql"
  params:
    connection_string: "sqlite:///./metrics.db"
    query: |
      SELECT
        datetime('{{ period_start }}', '+10 minutes') as period_time,
        COUNT(*) as value
      FROM events
      WHERE timestamp >= datetime('{{ period_start }}')
        AND timestamp < datetime('{{ period_finish }}')
```

## Configuration

### Connection String

The collector uses SQLAlchemy connection strings:

- **PostgreSQL**: `postgresql://[user[:password]@][host][:port][/database]`
- **MySQL**: `mysql://[user[:password]@][host][:port][/database]`
- **SQLite**: `sqlite:///path/to/database.db`

### Environment Variables

```bash
export POSTGRES_URL="postgresql://user:password@localhost:5432/analytics"
export MYSQL_URL="mysql://user:password@localhost:3306/ecommerce"
```

Then in config:

```yaml
collector:
  type: "sql"
  params:
    connection_string: "${POSTGRES_URL}"
    query: "SELECT ..."
```

### Query Requirements

Query must return:
- `value` column (float or int) - the metric value
- `timestamp` column (optional) - timestamp of measurement

If timestamp is not provided, current time is used.

## Storage

SQL collector can also be used as storage backend:

```yaml
storage:
  enabled: true
  type: "sql"
  params:
    connection_string: "${POSTGRES_URL}"
    datapoints_retention_days: 90
    save_detections: false  # Optional
```

This creates tables:
- `dtk_datapoints` - collected metric values
- `dtk_detections` - detection results (if save_detections=true)

## Examples

See `examples/sql/` directory for complete configurations.

## License

MIT
