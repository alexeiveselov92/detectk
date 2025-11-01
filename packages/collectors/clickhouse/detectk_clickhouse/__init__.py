"""ClickHouse collector and storage for DetectK.

This package provides:
- ClickHouseCollector: Collect metrics from ClickHouse queries
- ClickHouseStorage: Store metric history in ClickHouse

For usage examples, see: https://github.com/alexeiveselov92/detectk
"""

__version__ = "0.1.0"

from detectk_clickhouse.collector import ClickHouseCollector
from detectk_clickhouse.storage import ClickHouseStorage

__all__ = [
    "__version__",
    "ClickHouseCollector",
    "ClickHouseStorage",
]
