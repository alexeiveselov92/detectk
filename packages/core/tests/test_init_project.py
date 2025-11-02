"""Tests for project initialization."""

import shutil
from pathlib import Path

import pytest

from detectk.cli.init_project import (
    copy_examples,
    create_project_structure,
    init_git_repo,
)


class TestCreateProjectStructure:
    """Test project structure creation."""

    def test_creates_minimal_structure(self, tmp_path):
        """Test minimal project structure creation."""
        project_dir = tmp_path / "test_project"

        created = create_project_structure(
            project_dir,
            include_examples=False,
            minimal=True,
        )

        # Verify directory created
        assert project_dir.exists()
        assert project_dir.is_dir()

        # Verify essential files created
        assert (project_dir / "detectk_profiles.yaml.template").exists()
        assert (project_dir / ".env.template").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "README.md").exists()
        assert (project_dir / "metrics").exists()
        assert (project_dir / "metrics" / "example_metric.yaml").exists()

        # Verify examples directory NOT created in minimal mode
        assert not (project_dir / "examples").exists()

        # Verify created list contains files
        assert len(created) > 0

    def test_creates_full_structure(self, tmp_path):
        """Test full project structure with examples directory."""
        project_dir = tmp_path / "test_project"

        created = create_project_structure(
            project_dir,
            include_examples=True,
            minimal=False,
        )

        # Verify examples directory created
        assert (project_dir / "examples").exists()
        assert (project_dir / "examples").is_dir()

    def test_handles_existing_directory(self, tmp_path):
        """Test that existing directory is handled gracefully."""
        project_dir = tmp_path / "existing_project"
        project_dir.mkdir()

        # Should not raise exception
        created = create_project_structure(project_dir)

        # Files should still be created
        assert (project_dir / "README.md").exists()

    def test_profiles_template_content(self, tmp_path):
        """Test that profiles template contains expected content."""
        project_dir = tmp_path / "test_project"
        create_project_structure(project_dir)

        content = (project_dir / "detectk_profiles.yaml.template").read_text()

        # Verify template has essential sections
        assert "profiles:" in content
        assert "prod_clickhouse:" in content
        assert "staging_clickhouse:" in content
        assert "dev_sqlite:" in content
        assert "${CLICKHOUSE_PASSWORD}" in content

    def test_env_template_content(self, tmp_path):
        """Test that .env template contains expected content."""
        project_dir = tmp_path / "test_project"
        create_project_structure(project_dir)

        content = (project_dir / ".env.template").read_text()

        # Verify environment variables
        assert "export CLICKHOUSE_HOST=" in content
        assert "export CLICKHOUSE_PASSWORD=" in content
        assert "export SLACK_WEBHOOK=" in content
        assert "export MATTERMOST_WEBHOOK=" in content

    def test_gitignore_content(self, tmp_path):
        """Test that .gitignore contains credentials protection."""
        project_dir = tmp_path / "test_project"
        create_project_structure(project_dir)

        content = (project_dir / ".gitignore").read_text()

        # Verify credentials are gitignored
        assert "detectk_profiles.yaml" in content
        assert ".env" in content
        assert "*.local.yaml" in content

        # Verify common patterns
        assert "__pycache__/" in content
        assert "*.py[cod]" in content

    def test_readme_content(self, tmp_path):
        """Test that README contains setup instructions."""
        project_dir = tmp_path / "test_project"
        create_project_structure(project_dir)

        content = (project_dir / "README.md").read_text()

        # Verify project name in title
        assert "# test_project" in content

        # Verify essential sections
        assert "## Setup" in content
        assert "pip install detectk" in content
        assert "cp detectk_profiles.yaml.template" in content
        assert "dtk validate" in content
        assert "dtk run" in content

    def test_example_metric_content(self, tmp_path):
        """Test that example metric config is valid."""
        project_dir = tmp_path / "test_project"
        create_project_structure(project_dir)

        content = (project_dir / "metrics" / "example_metric.yaml").read_text()

        # Verify essential configuration sections
        assert "name:" in content
        assert "collector:" in content
        assert "detector:" in content
        assert "alerter:" in content
        assert "storage:" in content

        # Verify uses profile reference
        assert 'profile: "prod_clickhouse"' in content


class TestCopyExamples:
    """Test example copying functionality."""

    def test_copy_examples_from_source(self, tmp_path):
        """Test copying examples from source directory."""
        # Create fake source examples
        source_dir = tmp_path / "source_examples"
        source_dir.mkdir()

        threshold_dir = source_dir / "threshold"
        threshold_dir.mkdir()
        (threshold_dir / "simple.yaml").write_text("test: threshold")

        mad_dir = source_dir / "mad_seasonal"
        mad_dir.mkdir()
        (mad_dir / "hourly.yaml").write_text("test: mad")

        # Create project
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Copy examples
        copied = copy_examples(project_dir, source_dir)

        # Verify files copied
        assert copied == 2
        assert (project_dir / "examples" / "threshold" / "simple.yaml").exists()
        assert (project_dir / "examples" / "mad_seasonal" / "hourly.yaml").exists()

    def test_skip_if_source_not_exists(self, tmp_path):
        """Test that copying is skipped if source doesn't exist."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        non_existent = tmp_path / "non_existent"

        # Should not raise, just return 0
        copied = copy_examples(project_dir, non_existent)
        assert copied == 0

    def test_copy_examples_auto_detect(self, tmp_path):
        """Test auto-detection of examples directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Call without source_dir (auto-detect)
        # Will return 0 if package examples not found (expected in test environment)
        copied = copy_examples(project_dir, examples_source_dir=None)
        assert isinstance(copied, int)


class TestInitGitRepo:
    """Test git repository initialization."""

    def test_init_git_repo_success(self, tmp_path):
        """Test successful git repository initialization."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Initialize git
        result = init_git_repo(project_dir)

        # Verify git directory created
        assert (project_dir / ".git").exists()
        assert (project_dir / ".git").is_dir()
        assert result is True

    def test_init_git_handles_missing_git(self, tmp_path, monkeypatch):
        """Test that missing git binary is handled gracefully."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Mock subprocess to raise FileNotFoundError
        def mock_run(*args, **kwargs):
            raise FileNotFoundError("git not found")

        import subprocess

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should return False, not raise
        result = init_git_repo(project_dir)
        assert result is False

    def test_init_git_handles_error(self, tmp_path, monkeypatch):
        """Test that git errors are handled gracefully."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Mock subprocess to raise CalledProcessError
        def mock_run(*args, **kwargs):
            import subprocess

            raise subprocess.CalledProcessError(1, "git init")

        import subprocess

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should return False, not raise
        result = init_git_repo(project_dir)
        assert result is False


class TestProjectIntegration:
    """Integration tests for complete project initialization."""

    def test_complete_project_creation(self, tmp_path):
        """Test creating a complete project with all features."""
        project_dir = tmp_path / "my_metrics"

        # Create full structure
        created = create_project_structure(
            project_dir,
            include_examples=True,
            minimal=False,
        )

        # Initialize git
        git_success = init_git_repo(project_dir)

        # Verify complete structure
        assert (project_dir / "detectk_profiles.yaml.template").exists()
        assert (project_dir / ".env.template").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "README.md").exists()
        assert (project_dir / "metrics" / "example_metric.yaml").exists()
        assert (project_dir / "examples").exists()

        if git_success:
            assert (project_dir / ".git").exists()

        # Verify returned list
        assert len(created) >= 6

    def test_can_recreate_in_existing_directory(self, tmp_path):
        """Test that init can be run twice in same directory."""
        project_dir = tmp_path / "project"

        # First creation
        create_project_structure(project_dir)
        assert (project_dir / "README.md").exists()

        original_content = (project_dir / "README.md").read_text()

        # Second creation (should overwrite)
        create_project_structure(project_dir)

        # Files should still exist
        assert (project_dir / "README.md").exists()
        new_content = (project_dir / "README.md").read_text()

        # Content should be same (idempotent)
        assert new_content == original_content
