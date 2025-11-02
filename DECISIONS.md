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
    query: "SELECT count() FROM sessions"
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
       query: "SELECT count(DISTINCT user_id) as value FROM sessions"
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

