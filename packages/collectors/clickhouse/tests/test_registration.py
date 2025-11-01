"""Tests for ClickHouse components registration."""

import pytest

from detectk.registry import CollectorRegistry, StorageRegistry
from detectk_clickhouse import ClickHouseCollector, ClickHouseStorage


def test_clickhouse_collector_registered():
    """Test that ClickHouseCollector is registered in CollectorRegistry."""
    # Check that "clickhouse" is registered
    assert CollectorRegistry.is_registered("clickhouse")

    # Get the class
    collector_class = CollectorRegistry.get("clickhouse")
    assert collector_class is ClickHouseCollector


def test_clickhouse_storage_registered():
    """Test that ClickHouseStorage is registered in StorageRegistry."""
    # Check that "clickhouse" is registered
    assert StorageRegistry.is_registered("clickhouse")

    # Get the class
    storage_class = StorageRegistry.get("clickhouse")
    assert storage_class is ClickHouseStorage


def test_clickhouse_collector_in_list_all():
    """Test that ClickHouse collector appears in registry list."""
    all_collectors = CollectorRegistry.list_all()
    assert "clickhouse" in all_collectors


def test_clickhouse_storage_in_list_all():
    """Test that ClickHouse storage appears in registry list."""
    all_storages = StorageRegistry.list_all()
    assert "clickhouse" in all_storages
