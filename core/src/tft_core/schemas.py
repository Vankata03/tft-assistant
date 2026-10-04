"""Generate `schemas/messages.schema.json` from the message models.

`uv run tft-schemas` writes the file; `uv run tft-schemas --check` fails when
the committed file is stale. The shell generates its TypeScript types from it
(`npm run gen:types` in `ui/`).
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic.json_schema import models_json_schema

from tft_core.messages import SCHEMA_VERSION, CoreMessage, UiMessage

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "schemas" / "messages.schema.json"


def build_schema() -> dict:
    _, schema = models_json_schema(
        [(CoreMessage, "serialization"), (UiMessage, "serialization")],
        title="Messages",
        description=f"Core and shell WebSocket messages, schema version {SCHEMA_VERSION}.",
    )
    return schema


def render_schema() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    args = parser.parse_args()
    rendered = render_schema()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != rendered:
            sys.exit(f"{SCHEMA_PATH} is stale; run `uv run tft-schemas`")
        return
    SCHEMA_PATH.parent.mkdir(exist_ok=True)
    SCHEMA_PATH.write_bytes(rendered.encode("utf-8"))
    print(f"wrote {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
