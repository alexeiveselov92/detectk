# Connection Profiles Guide

Centralized database connection management for DetectK metrics.

## Why Use Profiles?

**Problem:** Without profiles, you duplicate connection params in every metric:

```yaml
# metric1.yaml
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    port: 9000
    database: "analytics"
    user: "${CLICKHOUSE_USER}"
    password: "${CLICKHOUSE_PASSWORD}"  # Duplicated!
    query: "SELECT ..."

# metric2.yaml - SAME connection params duplicated!
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"          # Duplicated!
    port: 9000                           # Duplicated!
    ...
```

**Solution:** Define connection once, reference everywhere:

```yaml
# detectk_profiles.yaml
profiles:
  clickhouse_analytics:
    type: "clickhouse"
    host: "${CLICKHOUSE_HOST}"
    port: 9000
    database: "analytics"
    user: "${CLICKHOUSE_USER}"
    password: "${CLICKHOUSE_PASSWORD}"

# metric1.yaml - SHORT!
collector:
  profile: "clickhouse_analytics"
  params:
    query: "SELECT ..."

# metric2.yaml - SHORT!
collector:
  profile: "clickhouse_analytics"
  params:
    query: "SELECT ..."
```

## Quick Start

### 1. Create Profiles File

```bash
# Copy template
cp detectk_profiles.yaml.template detectk_profiles.yaml

# Edit with your connections
vim detectk_profiles.yaml
```

### 2. Add to .gitignore

```bash
echo "detectk_profiles.yaml" >> .gitignore
```

### 3. Configure Profile

```yaml
# detectk_profiles.yaml
profiles:
  my_clickhouse:
    type: "clickhouse"
    host: "${CLICKHOUSE_HOST:-localhost}"
    port: 9000
    database: "analytics"
    user: "${CLICKHOUSE_USER:-default}"
    password: "${CLICKHOUSE_PASSWORD}"
```

### 4. Use in Metrics

```yaml
# configs/sessions.yaml
name: "sessions_10min"

collector:
  profile: "my_clickhouse"  # ← Reference profile
  params:
    query: "SELECT count() FROM sessions"

detector:
  type: "mad"
  params:
    window_size: "30 days"
```

### 5. Set Environment Variables

```bash
export CLICKHOUSE_HOST="prod-clickhouse.com"
export CLICKHOUSE_USER="detectk_user"
export CLICKHOUSE_PASSWORD="secret123"
```

### 6. Run

```bash
dtk run configs/sessions.yaml
```

## Profile Locations

DetectK searches for profiles in priority order:

1. **`./detectk_profiles.yaml`** - Local (highest priority)
2. **`~/.detectk/profiles.yaml`** - Global

**Use case:**
- Global (`~/.detectk/profiles.yaml`) - shared across all projects
- Local (`./detectk_profiles.yaml`) - project-specific connections

**Priority example:**
```yaml
# ~/.detectk/profiles.yaml (global)
profiles:
  clickhouse_analytics:
    host: "global-clickhouse.com"

# ./detectk_profiles.yaml (local - wins!)
profiles:
  clickhouse_analytics:
    host: "local-clickhouse.com"  # This one is used
```

## Configuration Options

### Profile Structure

```yaml
profiles:
  profile_name:          # Unique identifier
    type: "collector_type"  # Required: clickhouse, postgres, etc.
    # ... connection parameters specific to collector type
```

### ClickHouse Profile

```yaml
profiles:
  clickhouse_analytics:
    type: "clickhouse"
    host: "localhost"
    port: 9000
    database: "analytics"
    user: "default"
    password: "secret"
    # Optional parameters:
    timeout: 30
    retries: 3
    compression: true
```

### PostgreSQL Profile

```yaml
profiles:
  postgres_production:
    type: "postgres"
    host: "localhost"
    port: 5432
    database: "production"
    user: "postgres"
    password: "secret"
    # Or use connection string:
    # connection_string: "postgresql://user:pass@host:5432/db"
```

## Parameter Merging

DetectK merges parameters with this priority (highest to lowest):

1. **Explicit params** in metric config
2. **Profile params**
3. **Environment variable defaults** (handled by collector)

### Example: Override Profile Params

```yaml
# detectk_profiles.yaml
profiles:
  my_db:
    type: "clickhouse"
    host: "prod-host.com"
    port: 9000
    database: "analytics"

# metric.yaml
collector:
  profile: "my_db"
  params:
    host: "dev-host.com"  # ← Overrides profile's host
    query: "SELECT ..."

# Result: host="dev-host.com", port=9000, database="analytics"
```

### Example: Extend Profile Params

```yaml
# detectk_profiles.yaml
profiles:
  my_db:
    type: "clickhouse"
    host: "prod-host.com"
    port: 9000

# metric.yaml
collector:
  profile: "my_db"
  params:
    database: "logs"  # ← Adds database (not in profile)
    query: "SELECT ..."

# Result: host="prod-host.com", port=9000, database="logs"
```

## Three Ways to Configure Collector

DetectK supports three configuration patterns:

### 1. Profile Reference (Recommended)

**Use when:** Multiple metrics use same connection

```yaml
collector:
  profile: "clickhouse_analytics"
  params:
    query: "SELECT count() FROM sessions"
```

**Pros:**
- ✅ DRY - define once, use everywhere
- ✅ Easy to update (change one file, not 100)
- ✅ Secure (credentials in separate file)

### 2. Minimal (Env Var Defaults)

**Use when:** Simple setup, single database

```yaml
collector:
  type: "clickhouse"
  params:
    query: "SELECT count() FROM sessions"
    # host/port/database from $CLICKHOUSE_* env vars
```

**Pros:**
- ✅ Minimal config
- ✅ No additional files needed

**Cons:**
- ❌ Less flexible for multiple databases
- ❌ Relies on env vars being set

### 3. Full Explicit

**Use when:** Special connection params needed

```yaml
collector:
  type: "clickhouse"
  params:
    host: "special-host.com"
    port: 9001
    database: "special_db"
    query: "SELECT ..."
```

**Pros:**
- ✅ Full control
- ✅ Self-contained

**Cons:**
- ❌ Verbose
- ❌ Duplicated across metrics

## Security Best Practices

### 1. Never Commit Credentials

```bash
# Add to .gitignore
echo "detectk_profiles.yaml" >> .gitignore
echo ".detectk/" >> .gitignore
```

### 2. Use Environment Variables

```yaml
# Good: Use env vars for secrets
profiles:
  my_db:
    type: "clickhouse"
    password: "${CLICKHOUSE_PASSWORD}"  # ✅ From env

# Bad: Hardcoded secrets
profiles:
  my_db:
    type: "clickhouse"
    password: "secret123"  # ❌ Never do this!
```

### 3. Provide Defaults for Development

```yaml
profiles:
  my_db:
    type: "clickhouse"
    host: "${CLICKHOUSE_HOST:-localhost}"  # Default: localhost
    user: "${CLICKHOUSE_USER:-default}"    # Default: default
    password: "${CLICKHOUSE_PASSWORD}"     # No default (required)
```

### 4. Use Template File in Git

```bash
# In git (template with env vars)
detectk_profiles.yaml.template

# Not in git (actual credentials)
detectk_profiles.yaml   # ← in .gitignore
```

### 5. Different Profiles for Environments

```yaml
profiles:
  clickhouse_dev:
    host: "localhost"
    password: "dev_password"

  clickhouse_staging:
    host: "${STAGING_HOST}"
    password: "${STAGING_PASSWORD}"

  clickhouse_production:
    host: "${PROD_HOST}"
    password: "${PROD_PASSWORD}"
```

## Examples

See [examples/profiles/](.) for working examples:

- `profiles_example.yaml` - Sample profiles file
- `metric_with_profile.yaml` - Using profile in metric config
- `multi_database.yaml` - Multiple databases with different profiles

## Troubleshooting

### Profile not found

```
ConfigurationError: Profile 'my_db' not found. Available profiles: none
```

**Solution:**
1. Check profile file exists: `ls detectk_profiles.yaml`
2. Check profile name matches exactly (case-sensitive)
3. Check YAML syntax is valid
4. Check profiles are under `profiles:` key

### Profile has no type

```
ConfigurationError: Profile 'my_db' must specify 'type' field
```

**Solution:** Add `type` field to profile:

```yaml
profiles:
  my_db:
    type: "clickhouse"  # ← Add this
    host: "localhost"
```

### Environment variable not expanded

```yaml
# Profile
password: "${CLICKHOUSE_PASSWORD}"

# Error: literal string "${CLICKHOUSE_PASSWORD}" used
```

**Solution:** Ensure env var is set before running:

```bash
export CLICKHOUSE_PASSWORD="secret"
dtk run config.yaml
```

### Wrong database used

Profile has `database: "analytics"` but collector uses different database.

**Solution:** Override in metric config:

```yaml
collector:
  profile: "my_profile"
  params:
    database: "logs"  # Override profile's database
    query: "SELECT ..."
```

## Migration Guide

### From Explicit Configs to Profiles

**Before:**
```yaml
# 10 metric files with duplicated connection
# metric1.yaml, metric2.yaml, ..., metric10.yaml
collector:
  type: "clickhouse"
  params:
    host: "prod-host.com"
    port: 9000
    database: "analytics"
    query: "SELECT ..."
```

**After:**

1. Create `detectk_profiles.yaml`:
```yaml
profiles:
  clickhouse_analytics:
    type: "clickhouse"
    host: "prod-host.com"
    port: 9000
    database: "analytics"
```

2. Update all metrics (simple find-replace):
```yaml
# metric1.yaml, metric2.yaml, ..., metric10.yaml
collector:
  profile: "clickhouse_analytics"
  params:
    query: "SELECT ..."
```

3. Done! Now changing connection = edit one file, not 10.

## See Also

- [Configuration Guide](../../docs/configuration.md) - Full configuration reference
- [ClickHouse Collector](../../packages/collectors/clickhouse/README.md) - ClickHouse-specific params
- [Environment Variables](../../docs/environment_variables.md) - Env var patterns

---

**Note:** Profiles feature requires DetectK >= 0.2.0
