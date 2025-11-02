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
        COUNT(DISTINCT user_id) as value,
        NOW() as timestamp
      FROM sessions
      WHERE created_at >= NOW() - INTERVAL '10 minutes'

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
        COUNT(*) as value,
        NOW() as timestamp
      FROM orders
      WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
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
        COUNT(*) as value,
        datetime('now') as timestamp
      FROM events
      WHERE timestamp >= datetime('now', '-10 minutes')
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
