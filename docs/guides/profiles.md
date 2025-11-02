# Connection Profiles Guide

Connection Profiles allow you to define database credentials once and reuse them across multiple metrics. This keeps your metric configs clean and secure.

## Why Use Profiles?

**Without profiles** (repetitive, insecure):

```yaml
# metric1.yaml
collector:
  type: "clickhouse"
  params:
    host: "prod.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "hardcoded_password_bad!"  # ❌ Security risk
    query: |
      SELECT count() as value FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

# metric2.yaml - same credentials repeated
collector:
  type: "clickhouse"
  params:
    host: "prod.clickhouse.company.com"  # ❌ Duplication
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "hardcoded_password_bad!"  # ❌ Same password again
    query: |
      SELECT count() as value FROM purchases
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**With profiles** (DRY, secure):

```yaml
# detectk_profiles.yaml (NOT in git)
profiles:
  prod_clickhouse:
    type: "clickhouse"
    host: "prod.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${CLICKHOUSE_PASSWORD}"  # ✓ From environment

# metric1.yaml
collector:
  profile: "prod_clickhouse"  # ✓ Reference profile
  params:
    query: |
      SELECT count() as value FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

# metric2.yaml
collector:
  profile: "prod_clickhouse"  # ✓ Same profile
  params:
    query: |
      SELECT count() as value FROM purchases
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**Benefits:**
- ✅ **DRY** - Define connection once, use everywhere
- ✅ **Secure** - Credentials in separate file (not in git)
- ✅ **Flexible** - Change globally or override per metric
- ✅ **Clean** - Metric configs focus on business logic, not infrastructure

## Creating Profiles File

### Step 1: Create detectk_profiles.yaml

**Important:** This file should NOT be in git (add to .gitignore).

```yaml
# detectk_profiles.yaml

profiles:
  # Production ClickHouse
  prod_clickhouse:
    type: "clickhouse"
    host: "prod.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${CLICKHOUSE_PASSWORD}"  # From environment

  # Staging ClickHouse
  staging_clickhouse:
    type: "clickhouse"
    host: "staging.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${CLICKHOUSE_STAGING_PASSWORD}"

  # PostgreSQL warehouse
  postgres_warehouse:
    type: "sql"
    connection_string: "${POSTGRES_DSN}"

  # Development SQLite
  dev_sqlite:
    type: "sql"
    connection_string: "sqlite:///./dev_metrics.db"
```

### Step 2: Set Environment Variables

```bash
export CLICKHOUSE_PASSWORD="your_secure_password"
export CLICKHOUSE_STAGING_PASSWORD="staging_password"
export POSTGRES_DSN="postgresql://user:pass@host:5432/dbname"
```

**For production:**
```bash
# ~/.bashrc or /etc/environment
export CLICKHOUSE_PASSWORD="..."

# Or use secrets management
aws secretsmanager get-secret-value --secret-id detectk/clickhouse --query SecretString
```

### Step 3: Add to .gitignore

```bash
# .gitignore
detectk_profiles.yaml
*.local.yaml
```

## Using Profiles in Metrics

### Basic Usage

```yaml
name: "sessions_10min"

collector:
  profile: "prod_clickhouse"  # Reference profile by name
  params:
    query: |
      SELECT count() as value FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

storage:
  enabled: true
  profile: "prod_clickhouse"  # Can reuse same profile

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
```

### Override Profile Parameters

You can override specific parameters from the profile:

```yaml
collector:
  profile: "prod_clickhouse"
  params:
    database: "analytics_v2"  # Override database from profile
    query: |
      SELECT count() as value FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**Merged result:**
- `host`, `port`, `user`, `password` from profile
- `database` overridden to "analytics_v2"
- `query` added (not in profile)

### Hybrid Approach

Mix profile with inline params:

```yaml
# Use profile for connection
collector:
  profile: "prod_clickhouse"
  params:
    query: |
      SELECT count() as value FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

# Use inline connection for storage (different DB)
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "metrics.clickhouse.company.com"  # Different host
    port: 9000
    database: "detectk_storage"
    user: "${STORAGE_USER}"
    password: "${STORAGE_PASSWORD}"
```

## Profile Locations

DetectK searches for `detectk_profiles.yaml` in these locations (in order):

1. Current working directory: `./detectk_profiles.yaml`
2. User home directory: `~/.detectk/profiles.yaml`
3. System-wide: `/etc/detectk/profiles.yaml`
4. Custom path via environment: `DETECTK_PROFILES_PATH`

**Set custom location:**

```bash
export DETECTK_PROFILES_PATH="/opt/detectk/profiles.yaml"
```

## Profile Types

### ClickHouse Profile

```yaml
profiles:
  my_clickhouse:
    type: "clickhouse"
    host: "clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${CLICKHOUSE_PASSWORD}"
    secure: false  # Set to true for TLS

    # Optional connection pool settings
    pool_size: 10
    pool_timeout: 30
```

### PostgreSQL Profile

```yaml
profiles:
  my_postgres:
    type: "sql"
    connection_string: "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres.company.com:5432/analytics"

    # Or separate parameters
    # host: "postgres.company.com"
    # port: 5432
    # database: "analytics"
    # user: "${POSTGRES_USER}"
    # password: "${POSTGRES_PASSWORD}"
```

### MySQL Profile

```yaml
profiles:
  my_mysql:
    type: "sql"
    connection_string: "mysql+pymysql://${MYSQL_USER}:${MYSQL_PASSWORD}@mysql.company.com:3306/analytics"
```

### SQLite Profile

```yaml
profiles:
  local_dev:
    type: "sql"
    connection_string: "sqlite:///./metrics.db"
```

### HTTP/API Profile

```yaml
profiles:
  metrics_api:
    type: "http"
    base_url: "https://api.company.com"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
      X-API-Version: "v2"
    timeout: 30
```

## Multi-Environment Setup

Use different profiles for dev/staging/prod:

```yaml
# detectk_profiles.yaml

profiles:
  # Development
  dev:
    type: "sql"
    connection_string: "sqlite:///./dev_metrics.db"

  # Staging
  staging:
    type: "clickhouse"
    host: "staging.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk_staging"
    password: "${STAGING_PASSWORD}"

  # Production
  prod:
    type: "clickhouse"
    host: "prod.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk_prod"
    password: "${PROD_PASSWORD}"
```

**Switch environments:**

```yaml
# metric.yaml
collector:
  profile: "${DETECTK_ENV:-dev}"  # Default to dev, override with env var
  params:
    query: |
      SELECT count() as value FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

```bash
# Development
dtk run metric.yaml

# Staging
DETECTK_ENV=staging dtk run metric.yaml

# Production
DETECTK_ENV=prod dtk run metric.yaml
```

## Security Best Practices

### 1. Never Commit Profiles File

```bash
# .gitignore
detectk_profiles.yaml
.detectk/
*.local.yaml
```

### 2. Use Environment Variables

```yaml
# ✓ GOOD - from environment
profiles:
  prod:
    password: "${CLICKHOUSE_PASSWORD}"

# ✗ BAD - hardcoded
profiles:
  prod:
    password: "my_secret_password"
```

### 3. Use Secrets Management

**AWS Secrets Manager:**
```bash
export CLICKHOUSE_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id detectk/clickhouse \
  --query SecretString \
  --output text)
```

**HashiCorp Vault:**
```bash
export CLICKHOUSE_PASSWORD=$(vault kv get -field=password secret/detectk/clickhouse)
```

**Kubernetes Secrets:**
```yaml
# deployment.yaml
env:
  - name: CLICKHOUSE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: detectk-secrets
        key: clickhouse-password
```

### 4. Restrict File Permissions

```bash
chmod 600 detectk_profiles.yaml
chown detectk:detectk detectk_profiles.yaml
```

### 5. Separate Read/Write Access

Use read-only credentials for DetectK:

```sql
-- ClickHouse: Create read-only user
CREATE USER detectk_readonly IDENTIFIED BY 'password';
GRANT SELECT ON analytics.* TO detectk_readonly;

-- PostgreSQL: Create read-only user
CREATE USER detectk_readonly WITH PASSWORD 'password';
GRANT CONNECT ON DATABASE analytics TO detectk_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO detectk_readonly;
```

## Template Profiles

### Create Template

Provide `detectk_profiles.yaml.template` in git:

```yaml
# detectk_profiles.yaml.template
# Copy to detectk_profiles.yaml and fill in credentials

profiles:
  prod_clickhouse:
    type: "clickhouse"
    host: "REPLACE_WITH_HOST"
    port: 9000
    database: "analytics"
    user: "REPLACE_WITH_USER"
    password: "${CLICKHOUSE_PASSWORD}"  # Set in environment

  postgres_warehouse:
    type: "sql"
    connection_string: "${POSTGRES_DSN}"  # Set in environment
```

**Setup instructions:**

```bash
# 1. Copy template
cp detectk_profiles.yaml.template detectk_profiles.yaml

# 2. Edit with your values
vim detectk_profiles.yaml

# 3. Set environment variables
export CLICKHOUSE_PASSWORD="..."
export POSTGRES_DSN="..."

# 4. Test connection
dtk run metric.yaml
```

## Troubleshooting

### "Profile 'prod_clickhouse' not found"

**Cause:** Profile doesn't exist in detectk_profiles.yaml

**Solution:**
```bash
# Check profile file location
echo $DETECTK_PROFILES_PATH

# Verify file exists
ls -la detectk_profiles.yaml

# Check profile name matches
grep "prod_clickhouse:" detectk_profiles.yaml
```

### "Environment variable 'CLICKHOUSE_PASSWORD' not set"

**Cause:** Referenced env var not defined

**Solution:**
```bash
# Set the variable
export CLICKHOUSE_PASSWORD="your_password"

# Or check if it's set
echo $CLICKHOUSE_PASSWORD
```

### "Connection refused"

**Cause:** Profile has wrong host/port or firewall blocking

**Solution:**
```bash
# Test connection manually
clickhouse-client --host prod.clickhouse.company.com --port 9000

# Check firewall
telnet prod.clickhouse.company.com 9000
```

### Profile parameters not being used

**Cause:** Inline params override profile

**Solution:** Remove inline params to use profile defaults:

```yaml
# ✗ This overrides profile completely
collector:
  profile: "prod_clickhouse"
  type: "clickhouse"  # Remove this
  params:
    host: "..."       # Remove this

# ✓ This uses profile
collector:
  profile: "prod_clickhouse"
  params:
    query: |
      SELECT count() as value FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

## Advanced: Profile Validation

Validate all profiles before deployment:

```bash
# Validate profiles file
dtk validate --profiles detectk_profiles.yaml

# Test all profile connections
dtk test-profiles detectk_profiles.yaml
```

**Example validation:**

```python
# scripts/validate_profiles.py
from detectk.config.profiles import ProfileLoader

loader = ProfileLoader("detectk_profiles.yaml")

for name, profile in loader.profiles.items():
    print(f"Testing {name}...")
    try:
        # Test connection
        collector = CollectorRegistry.create(profile["type"], profile)
        collector.test_connection()
        print(f"  ✓ {name} OK")
    except Exception as e:
        print(f"  ✗ {name} FAILED: {e}")
```

## Examples

See [examples/profiles/](../../examples/profiles/) for complete examples:

- `detectk_profiles.yaml.template` - Template with all profile types
- `metric_with_profile.yaml` - Using profile in metric
- `multi_environment.yaml` - Dev/staging/prod setup

## Next Steps

- **[Quick Start Guide](quickstart.md)** - Get started with profiles
- **[Collectors Guide](collectors.md)** - Collector-specific connection details
- **[Configuration Reference](configuration.md)** - Complete schema
