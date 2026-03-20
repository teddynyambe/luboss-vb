"""Custom SQLAlchemy types."""
import json
from sqlalchemy.types import UserDefinedType, Text


class MySQLVector(UserDefinedType):
    """Store vector embeddings as JSON text (compatible with all MySQL versions)."""
    cache_ok = True

    def __init__(self, dim: int):
        self.dim = dim

    def get_col_spec(self, **kw) -> str:
        return "LONGTEXT"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, (list, tuple)):
                return json.dumps(value)
            return value
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    return value
            return value
        return process
