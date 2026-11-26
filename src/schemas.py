"""Import bridge to the schema owned by skills/structured-output.

Keep existing extraction/scoring imports stable without a second schema copy.
"""

import importlib.util
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "skills" / "structured-output" / "order_schema.py"
_name = "desk_order_schema"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, SCHEMA_PATH)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    try:
        _spec.loader.exec_module(_module)
    except Exception:
        del sys.modules[_name]
        raise

_schema = sys.modules[_name]
ExtractionModel = _schema.ExtractionModel
LineItem = _schema.LineItem
Intent = _schema.Intent
INTENT_PRIORITY = _schema.INTENT_PRIORITY
OrderRequest = _schema.OrderRequest
bedrock_schema = _schema.bedrock_schema
GroundingReport = _schema.GroundingReport
