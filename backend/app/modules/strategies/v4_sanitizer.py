"""
V4 Sanitizer - Converts numpy/Decimal types to JSON-safe Python types.

Prevents FastAPI serialization errors like:
  ValueError: [TypeError("'numpy.bool' object is not iterable")]

This is needed because the technical analysis service uses numpy for
calculations, and numpy types (numpy.float64, numpy.bool_, etc.) are
not natively JSON-serializable.
"""

from datetime import date, datetime
from decimal import Decimal


def sanitize_for_json(obj):
    """
    Recursively convert numpy/Decimal types to native Python types.

    Handles:
    - numpy.float64 -> float
    - numpy.int64 -> int
    - numpy.bool_ -> bool
    - Decimal -> float
    - date/datetime -> str (ISO format)
    - Nested dicts and lists
    """
    if obj is None:
        return None

    # Check for numpy types FIRST (without importing numpy)
    # numpy.bool_ is a subclass of Python int, so we must check type name
    # before isinstance checks
    obj_type = type(obj).__name__
    obj_module = type(obj).__module__

    # numpy types (check module to be precise)
    if obj_module == 'numpy':
        if 'bool' in obj_type:
            return bool(obj)
        elif 'float' in obj_type:
            return float(obj)
        elif 'int' in obj_type or 'uint' in obj_type:
            return int(obj)
        elif obj_type == 'ndarray':
            return [sanitize_for_json(item) for item in obj.tolist()]
        else:
            # Unknown numpy type - try float, then str
            try:
                return float(obj)
            except (TypeError, ValueError):
                return str(obj)

    # Python native types - return as-is
    if isinstance(obj, bool):  # Must check bool BEFORE int (bool is subclass of int)
        return obj
    elif isinstance(obj, (str, int, float)):
        return obj
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]

    # Try to convert unknown types
    try:
        return float(obj)
    except (TypeError, ValueError):
        return str(obj)
