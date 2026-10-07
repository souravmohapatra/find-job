"""Export only the API schema, without reading a CV or connecting to any service."""

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.main import create_app  # noqa: E402

output = root / "frontend/src/lib/openapi.json"
output.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
print("API schema exported to frontend/src/lib/openapi.json")
