"""Custom SQLAlchemy types for MySQL 9.0+."""
import json
from sqlalchemy.types import UserDefinedType


class MySQLVector(UserDefinedType):
    """MySQL 9.0 native VECTOR(N) column type for float embeddings."""
    cache_ok = True

    def __init__(self, dim: int):
        self.dim = dim

    def get_col_spec(self, **kw) -> str:
        return f"VECTOR({self.dim})"

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
            return value
        return process
