"""Project initialization for DetectK.

This module provides templates and logic for creating a complete DetectK project
structure with profiles, examples, and documentation.
"""

from pathlib import Path

# Template for detectk_profiles.yaml
PROFILES_TEMPLATE = """# DetectK Connection Profiles Template
#
# 1. Copy this file: cp detectk_profiles.yaml.template detectk_profiles.yaml
# 2. Fill in your credentials
# 3. Set environment variables or use inline values
#
# IMPORTANT: detectk_profiles.yaml is gitignored - safe to put credentials

profiles:
  # Production ClickHouse
  prod_clickhouse:
    type: "clickhouse"
    host: "REPLACE_WITH_YOUR_HOST"  # e.g., "analytics.company.com"
    port: 9000
    database: "REPLACE_WITH_DATABASE"  # e.g., "analytics"
    user: "REPLACE_WITH_USER"
    password: "${CLICKHOUSE_PASSWORD}"  # Set in .env

  # Staging environment
  staging_clickhouse:
    type: "clickhouse"
    host: "${STAGING_CLICKHOUSE_HOST}"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${STAGING_CLICKHOUSE_PASSWORD}"

  # Development (local)
  dev_sqlite:
    type: "sql"
    connection_string: "sqlite:///./metrics.db"
"""

# Template for .env
ENV_TEMPLATE = """# DetectK Environment Variables Template
#
# 1. Copy this file: cp .env.template .env
# 2. Fill in your values
# 3. Load with: source .env (or use direnv)
#
# IMPORTANT: .env is gitignored - safe for secrets

# ClickHouse Credentials
export CLICKHOUSE_HOST="localhost"
export CLICKHOUSE_PASSWORD="your_password_here"
export STAGING_CLICKHOUSE_HOST="staging.clickhouse.local"
export STAGING_CLICKHOUSE_PASSWORD="staging_password"

# Alerter Webhooks
export SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
export MATTERMOST_WEBHOOK="https://mattermost.company.com/hooks/YOUR_WEBHOOK"

# Optional: Telegram
# export TELEGRAM_BOT_TOKEN="your_bot_token"
# export TELEGRAM_CHAT_ID="your_chat_id"
"""

# Template for .gitignore
GITIGNORE_TEMPLATE = """# DetectK project gitignore

# Credentials (NEVER commit these!)
detectk_profiles.yaml
.env
*.local.yaml

# Python
__pycache__/
*.py[cod]
.venv/
venv/

# IDE
.vscode/
.idea/
*.swp

# Logs
logs/
*.log

# Test data
test_data/
*.db
*.sqlite
"""

# Template for README.md
README_TEMPLATE = """# {project_name}

DetectK project for monitoring production metrics.

## Setup

### 1. Install DetectK

```bash
pip install detectk detectk-clickhouse detectk-detectors detectk-alerters-mattermost detectk-alerters-slack
```

### 2. Configure Credentials

```bash
# Copy templates
cp detectk_profiles.yaml.template detectk_profiles.yaml
cp .env.template .env

# Edit with your credentials
vim detectk_profiles.yaml
vim .env

# Load environment variables
source .env
```

### 3. Validate Configuration

```bash
dtk validate metrics/example_metric.yaml
```

### 4. Run Your First Check

```bash
dtk run metrics/example_metric.yaml
```

## Project Structure

- `metrics/` - Your metric configurations
- `examples/` - Reference examples from DetectK{examples_note}
- `detectk_profiles.yaml` - Database connections (gitignored)
- `.env` - Environment variables (gitignored)

## Documentation

- [DetectK GitHub](https://github.com/alexeiveselov92/detectk)
- Quick Start Guide (see docs/guides/quickstart.md in DetectK repo)
- Configuration Reference (see docs/guides/ in DetectK repo)

## Common Commands

```bash
# Run single metric
dtk run metrics/sessions.yaml

# Run all metrics
dtk run metrics/

# Backtest
dtk backtest metrics/sessions.yaml --start 2024-01-01 --end 2024-02-01

# List available components
dtk list-collectors
dtk list-detectors
dtk list-alerters
```
"""

# Template for example_metric.yaml
EXAMPLE_METRIC_TEMPLATE = """# Example Metric Configuration
#
# This is a starter template. Customize for your use case:
# 1. Update collector query
# 2. Choose appropriate detector
# 3. Configure alerter

name: "example_sessions_10min"
description: "Monitor user sessions every 10 minutes"

# Data source (uses profile from detectk_profiles.yaml)
collector:
  profile: "prod_clickhouse"  # Reference to detectk_profiles.yaml
  params:
    query: |
      SELECT count(DISTINCT user_id) as value
      FROM sessions
      WHERE timestamp >= now() - INTERVAL 10 MINUTE

# Anomaly detection
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(now())"

# Alerting
alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
    cooldown_minutes: 60

# Storage for historical analysis
storage:
  enabled: true
  profile: "prod_clickhouse"
"""


def create_project_structure(
    directory: Path,
    include_examples: bool = True,
    minimal: bool = False,
) -> list[Path]:
    """Create DetectK project directory structure.

    Args:
        directory: Root directory for project
        include_examples: If True, copy example configurations
        minimal: If True, only create essential files

    Returns:
        List of created file paths

    Raises:
        OSError: If directory creation fails
    """
    created_files: list[Path] = []

    # Create directory structure
    directory.mkdir(parents=True, exist_ok=True)
    created_files.append(directory)

    # Create subdirectories
    metrics_dir = directory / "metrics"
    metrics_dir.mkdir(exist_ok=True)
    created_files.append(metrics_dir)

    if include_examples and not minimal:
        examples_dir = directory / "examples"
        examples_dir.mkdir(exist_ok=True)
        created_files.append(examples_dir)

    # Create template files
    profiles_template_path = directory / "detectk_profiles.yaml.template"
    profiles_template_path.write_text(PROFILES_TEMPLATE)
    created_files.append(profiles_template_path)

    env_template_path = directory / ".env.template"
    env_template_path.write_text(ENV_TEMPLATE)
    created_files.append(env_template_path)

    gitignore_path = directory / ".gitignore"
    gitignore_path.write_text(GITIGNORE_TEMPLATE)
    created_files.append(gitignore_path)

    # Create README
    project_name = directory.name if directory.name != "." else "My DetectK Project"
    examples_note = " (optional)" if include_examples and not minimal else ""
    readme_content = README_TEMPLATE.format(
        project_name=project_name, examples_note=examples_note
    )
    readme_path = directory / "README.md"
    readme_path.write_text(readme_content)
    created_files.append(readme_path)

    # Create example metric config
    example_metric_path = metrics_dir / "example_metric.yaml"
    example_metric_path.write_text(EXAMPLE_METRIC_TEMPLATE)
    created_files.append(example_metric_path)

    return created_files


def copy_examples(project_dir: Path, examples_source_dir: Path | None = None) -> int:
    """Copy example configurations to project.

    Args:
        project_dir: Project root directory
        examples_source_dir: Source directory with examples (optional)

    Returns:
        Number of files copied

    Note:
        If examples_source_dir is None, tries to find examples in package.
        If not found, skips copying.
    """
    if examples_source_dir is None:
        # Try to find examples in package
        # This would be the installed package location
        import detectk

        package_dir = Path(detectk.__file__).parent.parent.parent
        potential_examples = package_dir / "examples"

        if not potential_examples.exists():
            # Not found, skip
            return 0

        examples_source_dir = potential_examples

    if not examples_source_dir.exists():
        return 0

    examples_dest = project_dir / "examples"
    examples_dest.mkdir(exist_ok=True)

    # Copy example directories
    copied = 0
    for subdir in examples_source_dir.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("."):
            dest_subdir = examples_dest / subdir.name
            dest_subdir.mkdir(exist_ok=True)

            # Copy YAML files
            for yaml_file in subdir.glob("*.yaml"):
                dest_file = dest_subdir / yaml_file.name
                dest_file.write_text(yaml_file.read_text())
                copied += 1

    return copied


def init_git_repo(directory: Path) -> bool:
    """Initialize git repository in directory.

    Args:
        directory: Directory to initialize

    Returns:
        True if successful, False otherwise
    """
    import subprocess

    try:
        subprocess.run(
            ["git", "init"],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
