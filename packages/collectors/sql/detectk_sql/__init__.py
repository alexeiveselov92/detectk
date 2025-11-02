"""DetectK SQL collectors - Generic SQL support for PostgreSQL, MySQL, SQLite."""

from detectk_sql.collector import GenericSQLCollector
from detectk_sql.storage import SQLStorage

__version__ = "0.1.0"

__all__ = ["GenericSQLCollector", "SQLStorage"]
