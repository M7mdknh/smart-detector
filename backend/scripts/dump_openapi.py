"""Dumps the FastAPI OpenAPI schema to JSON without starting a live server
(app.openapi() is a pure function over the already-declared routes) -- so
`make generate-api` never needs a running production server, per the task's
requirement.
"""

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

OUT_PATH = REPO_ROOT / "frontend" / "openapi.json"


def main():
    from app.main import app

    schema = app.openapi()
    OUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
