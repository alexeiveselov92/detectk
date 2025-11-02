# DetectK Architectural Decisions

**Last Updated:** 2025-11-02

This document contains detailed rationale, examples, and trade-offs for major architectural decisions made during DetectK development.

For high-level overview, see [CLAUDE.md](CLAUDE.md)

---

## Key Architectural Decisions

### Decision 1: CLI Naming - `dtk` (3 letters)

**Problem:** Need concise CLI command, but `detectk` is 7 characters.

**Solution:** Use `dtk` (like `dbt`, `git`, `npm`)

```bash
# Package name (clarity)
pip install detectk

# CLI command (brevity)
dtk run configs/sessions.yaml
dtk backtest configs/sessions.yaml
dtk validate configs/sessions.yaml
```

**Rationale:** Industry standard for data tools is 3 characters. Fast to type in daily use.

---

### Decision 2: Storage Schema - `dtk_*` Tables

**Problem:** Where to store collected metrics and detection results?

**Solution:** Two shared tables with `dtk_` prefix:

```sql
-- Collected metric values (required)
dtk_datapoints (
  id, metric_name, collected_at, value, context JSONB
)

-- Detection results (optional, for audit)
dtk_detections (
  id, metric_name, detector_id, detected_at,
  value, is_anomaly, score, bounds, direction,
  alert_sent, detector_type, detector_params, context
)
```

**Key points:**
- **Shared across all metrics** (scalable: 1000 metrics = 2 tables, not 2000)
- **JSONB context** - flexible seasonal features without schema migrations
- **`dtk_` prefix** - clear ownership, short (dtk = CLI name)
- **`detector_id`** - supports multiple detectors per metric (A/B testing)

**Rationale:**
- ✅ Scales to thousands of metrics
- ✅ Cross-metric queries possible
- ✅ No hardcoded seasonal columns
- ✅ Simple schema management

---

### Decision 3: Multi-Detector Architecture

**Problem:** One metric might need multiple detection strategies (A/B testing, parameter tuning).

**Solution:** Auto-generated deterministic detector IDs

```yaml
# Single detector (backward compatible)
detector:
  type: "mad"
  params: {window_size: "30 days", n_sigma: 3.0}
  # ID auto-generated: "a1b2c3d4" (hash of type + normalized params)

# Multiple detectors (A/B testing)
detectors:
  - type: "mad"
    params: {n_sigma: 3.0}  # Auto ID: "a1b2c3d4"

  - type: "mad"
    params: {n_sigma: 5.0}  # Auto ID: "b2c3d4e5" (different params)

  - id: "custom_id"  # Manual override
    type: "zscore"
    params: {window_size: "7 days"}
```

**Key features:**
- **Deterministic IDs** - 8-char hash from `type` + normalized params
- **Parameter normalization** - removes defaults before hashing (consistency)
- **Composite key** - `(metric_name, detector_id, detected_at)` in storage

**Use case:** Compare detector performance before choosing best strategy.

---

### Decision 4: Alerter Radical Simplicity

**Problem:** AlertAnalyzer abstraction was over-engineering.

**Solution:** Alerters only handle: **format + send + cooldown**

**NOT alerter's job:**
- ❌ Consecutive anomaly checking → tune detector n_sigma instead
- ❌ Direction filtering → use appropriate detector
- ❌ Min deviation thresholds → tune detector parameters

**Alerter's ONLY job:**
```python
def send(detection: DetectionResult) -> bool:
    if not detection.is_anomaly:
        return False
    if self._in_cooldown(metric_name):
        return False
    self._send_webhook(message)
    return True
```

**Philosophy:** Simple is better than complex. Detector decides WHAT is anomalous, alerter just sends.

**Statistics:** 310 lines (simple) vs 600+ lines (old complex approach)

---

### Decision 5: Connection Profiles (Hybrid Approach)

**Problem:** Duplicating connection params across hundreds of metric configs.

**Solution:** Three ways to configure collector:

**1. Profile reference (recommended - DRY):**
```yaml
# detectk_profiles.yaml (gitignored)
profiles:
  clickhouse_analytics:
    type: "clickhouse"
    host: "${CLICKHOUSE_HOST}"
    database: "analytics"
    password: "${CLICKHOUSE_PASSWORD}"

# metric.yaml (short!)
collector:
  profile: "clickhouse_analytics"
  params:
    query: |
      SELECT
        toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
        count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

**2. Minimal (env defaults):**
```yaml
collector:
  type: "clickhouse"
  params:
    query: "SELECT ..."
    # host/port/database from $CLICKHOUSE_* env vars
```

**3. Full explicit (special cases):**
```yaml
collector:
  type: "clickhouse"
  params:
    host: "special-host.com"
    port: 9001
    query: "SELECT ..."
```

**Priority:** Explicit params > Profile > Env vars > Defaults

**Rationale:**
- ✅ DRY - one connection definition for 100 metrics
- ✅ Secure - credentials in gitignored file
- ✅ Flexible - override profile per metric if needed

**Files:** `./detectk_profiles.yaml` (local, highest priority) > `~/.detectk/profiles.yaml` (global)

---

### Decision 6: Backtesting = Production Code

**Problem:** Need to test detectors on historical data before production.

**Solution:** Reuse SAME code path!

```python
# Production (one check)
checker.execute(config_path, execution_time=None)

# Backtesting (iterate through time)
for time in time_range(start, end, step):
    checker.execute(config_path, execution_time=time)
```

**Philosophy:** What you test = what you deploy. No separate backtest logic.

**CLI:**
```bash
dtk backtest config.yaml          # Run simulation
dtk backtest config.yaml -o out.csv  # Save results
```

**Benefits:**
- ✅ Tests actual production code
- ✅ No code duplication
- ✅ Simple architecture

---

### Decision 7: File-Based CLI (Not Name-Based)

**Problem:** Should CLI use file paths or logical names?

**Options:**
- File-based: `dtk run configs/sessions.yaml` (explicit)
- Name-based: `dtk run sessions` (magic resolution, like dbt)

**Solution:** File-based

**Rationale:**
- ✅ No strict project structure required
- ✅ Works with any file location
- ✅ What you see is what you get (WYSIWYG)
- ✅ Simpler than magic name resolution

**Comparison:**
- dbt: name-based (strict `models/` structure required)
- terraform: file-based (flexible)
- DetectK: file-based (flexible, like terraform)

---

### Decision 8: Default Alert Format - No Emojis

**Problem:** Slippery slope from old code - emojis hardcoded in default format.

**Analysis:**
- **Emojis in defaults:**
  - ❌ Not accessible (screen readers read "fire emoji")
  - ❌ Don't work in plain text (email, SMS, logs)
  - ❌ May look unprofessional in corporate environments

**Solution:** Simple, professional default

```
**ANOMALY DETECTED: sessions_10min**

Value: 1234.50
Expected range: 900.00 - 1100.00
Anomaly score: 4.20 sigma
Direction: up
Deviation: +15.0%

Time: 2024-11-02 14:30:00
Detector: type=mad, window=30 days, threshold=3.0 sigma
```

**Emojis → optional via custom templates:**
```yaml
alerter:
  type: "mattermost"
  params:
    message_template: |
      🚨 **ANOMALY** {{ metric_name }}
      📊 Value: {{ value }}
```

**Philosophy:** Default = universal (works everywhere). Fancy = opt-in via templates.

---

### Decision 9: Project Initialization - `dtk init-project`

**Problem:** After installing DetectK, analysts have no clear path to set up a monitoring project. Current `dtk init` only creates a single config file with no examples, profile templates, or project structure guidance.

**User story:**
```
As an analyst,
I want to quickly set up a DetectK project,
So that I can start monitoring metrics without reading docs.
```

**Solution:** New `dtk init-project` command that creates complete project structure

**Generated structure:**
```
my-metrics-monitoring/
├── detectk_profiles.yaml.template    # Credential template (NOT in git)
├── detectk_profiles.yaml             # User fills this (gitignored)
├── .env.template                     # Environment variables template
├── .env                              # User fills this (gitignored)
├── .gitignore                        # DetectK-specific gitignore
├── README.md                         # Project setup instructions
├── metrics/                          # User's metric configs
│   └── example_metric.yaml           # One example to get started
└── examples/                         # Reference examples (optional)
    ├── threshold/
    ├── mad_seasonal/
    ├── backtesting/
    └── missing_data/
```

**Command options:**
```bash
# Basic: Initialize in current directory
dtk init-project

# Create new directory
dtk init-project my-metrics-monitoring

# Interactive mode (asks questions)
dtk init-project --interactive

# With specific database
dtk init-project --database clickhouse

# Minimal (no examples)
dtk init-project --minimal
```

**Key files created:**

1. **detectk_profiles.yaml.template** - Connection profiles with placeholders
   ```yaml
   # Template with instructions
   profiles:
     prod_clickhouse:
       type: "clickhouse"
       host: "REPLACE_WITH_YOUR_HOST"
       password: "${CLICKHOUSE_PASSWORD}"  # Set in .env
   ```

2. **.env.template** - Environment variables template
   ```bash
   export CLICKHOUSE_HOST="localhost"
   export CLICKHOUSE_PASSWORD="your_password_here"
   export SLACK_WEBHOOK="https://hooks.slack.com/..."
   ```

3. **.gitignore** - Credentials protection
   ```
   # Credentials (NEVER commit these!)
   detectk_profiles.yaml
   .env
   *.local.yaml
   ```

4. **README.md** - Setup instructions with commands
   ```markdown
   ## Setup
   1. cp detectk_profiles.yaml.template detectk_profiles.yaml
   2. cp .env.template .env
   3. Edit with your credentials
   4. dtk validate metrics/example_metric.yaml
   5. dtk run metrics/example_metric.yaml
   ```

5. **metrics/example_metric.yaml** - Starter config
   ```yaml
   name: "example_sessions_10min"
   collector:
     profile: "prod_clickhouse"  # Reference to detectk_profiles.yaml
     params:
       query: |
         SELECT
           toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
           count(DISTINCT user_id) as value
         FROM sessions
         WHERE timestamp >= toDateTime('{{ period_start }}')
           AND timestamp < toDateTime('{{ period_finish }}')
   detector:
     type: "mad"
     params: {window_size: "30 days", n_sigma: 3.0}
   alerter:
     type: "slack"
     params:
       webhook_url: "${SLACK_WEBHOOK}"
   ```

**Interactive mode flow:**
```bash
$ dtk init-project --interactive

╔════════════════════════════════════════════════════════╗
║         DetectK Project Initialization                 ║
╚════════════════════════════════════════════════════════╝

? Project name: my-metrics-monitoring
? Primary database: ClickHouse / PostgreSQL / MySQL / SQLite
? Include example configurations? (Y/n): Y
? Include reference documentation? (Y/n): Y
? Initialize git repository? (Y/n): Y

Creating project structure...
✓ Created detectk_profiles.yaml.template
✓ Created .env.template
✓ Created .gitignore
✓ Created README.md
✓ Created metrics/example_metric.yaml
✓ Copied 5 example configurations
✓ Initialized git repository

Next steps:
1. cd my-metrics-monitoring
2. cp detectk_profiles.yaml.template detectk_profiles.yaml
3. cp .env.template .env
4. Edit detectk_profiles.yaml and .env with your credentials
5. dtk validate metrics/example_metric.yaml
6. dtk run metrics/example_metric.yaml

Documentation: https://docs.detectk.io/guides/quickstart
```

**Rationale:**

✅ **Fast onboarding** - Single command creates everything needed
✅ **Best practices built-in** - .gitignore, templates, examples included
✅ **Secure by default** - Credentials in gitignored files with templates
✅ **Clear structure** - Obvious where to put metrics, examples for reference
✅ **Guided experience** - README with step-by-step instructions
✅ **Inspired by dbt** - Similar pattern to `dbt init` (proven UX)

**Comparison with alternatives:**

- **Option A (Chosen):** Single command with flags
  - ✅ Fast onboarding, best practices built-in
  - ➖ Creates many files (might overwhelm)

- **Option B:** Wizard (more interactive)
  - ✅ Guided experience, only creates what user needs
  - ➖ Slower, more complex to implement

- **Option C:** Separate commands
  - ✅ Granular control
  - ➖ Too many steps, easy to forget something

**Implementation status:**
- **Approved:** 2025-11-02
- **Design:** Complete (see `/tmp/project_init_design.md` for full spec)
- **Implementation:** Pending (Phase 3 or 4)
- **Priority:** High (critical for user onboarding experience)

**Next steps when implementing:**
1. Add `init-project` command to CLI
2. Create template files as embedded strings or files in package
3. Copy example configs from library
4. Add interactive mode with prompts (optional, use `click.prompt`)
5. Update quickstart documentation
6. Add tests for project structure generation

---


---

## Decision 18: Time Series Data Collection Architecture

**Date:** 2025-11-02

**Problem:** Original implementation collected single aggregated values (1 row per query). This was inefficient for bulk loading and didn't work well with time series algorithms that need historical context.

**Decision:** Implement `collect_bulk(period_start, period_finish)` that returns multiple (timestamp, value) rows.

**Rationale:**

1. **Efficiency:** ONE query returns ALL data points for a time range
   - Old: 4,320 queries for 30 days of 10-min data
   - New: 1 query for 30 days of 10-min data

2. **Simplicity:** Analyst writes ONE query with variables
   - Same query works for real-time (10 min) and bulk loading (30 days)
   - No separate logic for different time ranges

3. **Flexibility:** Query renders on each call with different periods
   - Collector stores query as Jinja2 template
   - Renders with `period_start`, `period_finish` on each `collect_bulk()` call

**Example Query:**

```sql
SELECT
    toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
    count() AS value
FROM events
WHERE timestamp >= toDateTime('{{ period_start }}')
  AND timestamp < toDateTime('{{ period_finish }}')
GROUP BY period_time
ORDER BY period_time
```

**Implementation:**

```python
class ClickHouseCollector(BaseCollector):
    def __init__(self, config):
        self.query_template = config["query"]  # Store with {{ }}
    
    def collect_bulk(self, period_start, period_finish):
        # Render query with specific period
        query = Template(self.query_template).render(
            period_start=period_start.isoformat(),
            period_finish=period_finish.isoformat(),
        )
        
        result = client.execute(query)
        return [DataPoint(timestamp=row[0], value=row[1]) for row in result]
```

**Trade-offs:**

✅ **Pros:**
- Much more efficient (1 query vs thousands)
- Works with any time range
- Supports time series algorithms
- Simpler code (no iteration)

❌ **Cons:**
- Slightly more complex query (must include GROUP BY)
- Query must be written to return time series

**Alternatives Considered:**

1. **Keep single-point collection** → Rejected (too inefficient)
2. **Separate methods for real-time vs bulk** → Rejected (code duplication)
3. **Collector decides time range** → Rejected (less flexible)

---

## Decision 19: Remove BacktestRunner - Use Normal Pipeline

**Date:** 2025-11-02

**Problem:** BacktestRunner was a separate class that iterated through time steps, calling `collect()` thousands of times for historical data. This was inefficient and complex.

**Realization:** "Backtesting" is just normal data loading with alerts disabled!

**Decision:** Remove BacktestRunner entirely. Use normal pipeline with `alerter.enabled = false`.

**Rationale:**

There's NO difference between:
- Production monitoring (continuous, alerts enabled)
- Historical data loading (one-time, alerts disabled)

It's the SAME code, just different config:

**Before (with BacktestRunner):**
```python
# Iterate 4,320 times for 30 days of 10-min data
for current_time in time_steps:
    result = checker.execute(config, current_time)  # 1 query → 1 row
# Total: 4,320 queries
```

**After (without BacktestRunner):**
```python
# Call once with time range
points = collector.collect_bulk(start, end)  # 1 query → 4,320 rows
storage.save_datapoints_bulk(metric_name, points)
```

**Migration:**

**OLD (BacktestConfig):**
```yaml
backtest:
  enabled: true
  data_load_start: "2024-01-01"
  detection_start: "2024-02-01"
  detection_end: "2024-03-01"
  step_interval: "10 minutes"
```

**NEW (ScheduleConfig):**
```yaml
schedule:
  start_time: "2024-01-01"
  end_time: "2024-03-01"
  interval: "10 minutes"
  batch_load_days: 30  # Load in 30-day batches

alerter:
  enabled: false  # NO alerts during historical load
```

**Trade-offs:**

✅ **Pros:**
- Simpler code (no BacktestRunner class)
- Same code path for production and historical
- Much faster (1 query vs thousands)
- Easier to understand

❌ **Cons:**
- No separate "backtest" mode (but this is good!)

**Implementation:**

Removed:
- `detectk/backtest.py` (BacktestRunner class)
- `dtk backtest` CLI command
- BacktestConfig from config models

Added:
- ScheduleConfig (unified scheduling)
- `alerter.enabled` flag
- Checkpoint system for resuming loads

---

## Decision 20: ConfigLoader Must NOT Render Collector Queries

**Date:** 2025-11-02

**Problem:** ConfigLoader was rendering ENTIRE config as Jinja2 template at load time. This made `{{ period_start }}` static, preventing collectors from calling `collect_bulk()` with different time ranges.

**Example of broken behavior:**
```yaml
# Config loaded at 10:00 AM
collector:
  params:
    query: |
      WHERE timestamp >= '{{ execution_time }}'  # Rendered at load time!
```

After ConfigLoader: `WHERE timestamp >= '2024-11-02 10:00'` (hardcoded!)

Collector can't change this later → can't bulk load historical data!

**Decision:** ConfigLoader does NOT render `collector.params.query` field. Preserves `{{ }}` intact.

**Implementation:**

Changed ConfigLoader processing order:

**Before:**
1. Substitute env vars: `${VAR_NAME}` → value
2. Render ENTIRE file as Jinja2 template
3. Parse YAML

**After:**
1. Substitute env vars: `${VAR_NAME}` → value
2. Parse YAML (NO rendering)
3. Selectively render Jinja2 EXCEPT `collector.params.query`

**Code:**

```python
def _process_dict_templates(self, data, template_context, path=""):
    # Skip rendering collector.params.query
    if path == "collector.params.query":
        return data  # Leave {{ period_start }}, {{ period_finish }} intact
    
    # Render other fields
    if isinstance(data, str) and "{{" in data:
        return Template(data).render(**template_context)
    
    return data
```

**Rationale:**

Collector needs to render query on EACH call with different periods:
- Real-time: `collect_bulk(now-10min, now)`
- Bulk load: `collect_bulk(2024-01-01, 2024-01-31)`

If ConfigLoader rendered query at load time, it would be static → impossible to change periods!

**Trade-offs:**

✅ **Pros:**
- Collectors can render queries dynamically
- Same query works for any time range
- Enables bulk loading

❌ **Cons:**
- Slightly more complex ConfigLoader logic

**Critical:** Without this fix, time series architecture doesn't work!

---

## Decision 21: Flexible Column Naming with Explicit Mapping

**Date:** 2025-11-02

**Problem:** How to let analyst name query result columns however they want, while DetectK knows which column is timestamp and which is value?

**Decision:** Add explicit column mapping in CollectorConfig.

**Implementation:**

```yaml
collector:
  params:
    query: |
      SELECT
        my_custom_timestamp AS ts,    # Analyst chooses name
        my_metric_value AS val         # Analyst chooses name
      FROM ...
    timestamp_column: "ts"    # Tell DetectK which is timestamp
    value_column: "val"       # Tell DetectK which is value
    context_columns: ["hour_of_day"]  # Optional seasonal features
```

**Collector uses mapping to extract values:**

```python
timestamp = row[self.timestamp_column]  # row["ts"]
value = row[self.value_column]          # row["val"]

if self.context_columns:
    context = {col: row[col] for col in self.context_columns}
```

**Rationale:**

1. **Flexibility:** Analyst can use database conventions (e.g., `period_time`, `metric_value`)
2. **No hardcoded names:** DetectK doesn't assume column names
3. **Context support:** Optional seasonal features without schema changes

**Defaults:**

```python
timestamp_column: str = "period_time"  # Default
value_column: str = "value"           # Default
context_columns: list[str] | None = None  # Optional
```

**Trade-offs:**

✅ **Pros:**
- Analyst controls column naming
- Works with any database conventions
- Easy to add context/metadata

❌ **Cons:**
- Extra config (but has sensible defaults)

---

## Decision 22: ReplacingMergeTree for Automatic Deduplication

**Date:** 2025-11-02

**Problem:** When bulk loading historical data, interruptions mean some data loaded twice. How to prevent duplicates without manual deduplication?

**Decision:** Use ClickHouse ReplacingMergeTree engine for `dtk_datapoints` table.

**Implementation:**

```sql
CREATE TABLE dtk_datapoints (
    metric_name String,
    collected_at DateTime64(3),
    value Float64,
    is_missing UInt8,
    context String
) ENGINE = ReplacingMergeTree()  -- Automatic deduplication!
ORDER BY (metric_name, collected_at);
```

**How It Works:**

Rows with same `(metric_name, collected_at)` are automatically deduplicated during merges:

```sql
-- Insert same data twice
INSERT INTO dtk_datapoints VALUES ('metric', '2024-11-02 14:00', 100, 0, '{}');
INSERT INTO dtk_datapoints VALUES ('metric', '2024-11-02 14:00', 100, 0, '{}');

-- After merge: only 1 row
SELECT * FROM dtk_datapoints WHERE metric_name = 'metric';
```

**Benefits:**

1. **Idempotent loads:** Safe to re-run bulk loading without checking what's already loaded
2. **Crash recovery:** Resume interrupted loads without worrying about duplicates
3. **Corrected data:** Re-load corrected data, old data replaced automatically

**Checkpoint System:**

Even with deduplication, checkpoint system helps skip already-loaded ranges:

```python
last = storage.get_last_loaded_timestamp("metric")
if last:
    start = last + timedelta(minutes=10)  # Resume from here
```

**Trade-offs:**

✅ **Pros:**
- Automatic deduplication (no manual logic)
- Safe to re-load data
- Crash recovery without state management

❌ **Cons:**
- ClickHouse-specific (but PostgreSQL has ON CONFLICT UPDATE)
- Slight performance overhead during merges (minimal)

**Alternatives Considered:**

1. **Manual deduplication** → Rejected (complex, error-prone)
2. **Check before insert** → Rejected (slow, race conditions)
3. **UNIQUE constraint** → Rejected (not supported in MergeTree)

---

## Decision 23: Batch Loading for Memory Efficiency

**Date:** 2025-11-02

**Problem:** Loading 1 year of 10-minute data = ~52,560 rows in one query. This can cause memory issues and slow queries.

**Decision:** Load in configurable batches (default: 30 days).

**Implementation:**

```yaml
schedule:
  start_time: "2024-01-01"
  end_time: "2024-12-31"
  interval: "10 minutes"
  batch_load_days: 30  # Load in 30-day batches
```

**Execution:**

```python
batches = calculate_batches(
    start="2024-01-01",
    end="2024-12-31",
    batch_days=30
)
# Results: [(2024-01-01, 2024-01-31), (2024-02-01, 2024-02-29), ...]

for batch_start, batch_end in batches:
    points = collector.collect_bulk(batch_start, batch_end)  # ~4,464 points
    storage.save_datapoints_bulk(metric_name, points)
```

**Benefits:**

1. **Memory efficient:** Process 4,464 points at a time instead of 52,560
2. **Progress tracking:** Can log "Loaded batch 3/12"
3. **Checkpoint friendly:** If crash, resume from last completed batch
4. **Database friendly:** Smaller queries are faster and less resource-intensive

**Configurable batch size:**
- Small intervals (1 min): Use larger batches (60 days)
- Large intervals (1 hour): Use smaller batches (7 days)

**Trade-offs:**

✅ **Pros:**
- Memory efficient
- Resumable
- Progress visibility

❌ **Cons:**
- Multiple queries instead of one (but still efficient)

---
