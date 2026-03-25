"""Custom SQLAlchemy types."""
import json
from sqlalchemy import func
from sqlalchemy.types import UserDefinedType


class MySQLVector(UserDefinedType):
    """Store vector embeddings using MySQL native VECTOR type."""
    cache_ok = True

    def __init__(self, dim: int):
        self.dim = dim

    def get_col_spec(self, **kw) -> str:
        return f"VECTOR({self.dim})"

    def bind_expression(self, bindvalue):
        """Wrap bound value with STRING_TO_VECTOR() for INSERT/UPDATE."""
        return func.STRING_TO_VECTOR(bindvalue)

    def column_expression(self, col):
        """Wrap column with VECTOR_TO_STRING() for SELECT."""
        return func.VECTOR_TO_STRING(col)

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
