"""Write the API's OpenAPI schema to frontend/src/lib/openapi.json.

The frontend generates its TypeScript types from this file
(`npm run gen:api`), and `tests/test_openapi_sync.py` fails if it drifts from
the backend, so frontend types always match the Pydantic response models.

Usage:  python -m scripts.export_openapi
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "src" / "lib" / "openapi.json"


def build_schema() -> dict:
    os.environ.setdefault("AUTH_ENABLED", "true")
    sys.path.insert(0, str(ROOT))
    from app.main import app

    return app.openapi()


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render(build_schema()), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
