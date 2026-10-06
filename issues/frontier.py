"""List open, unassigned, unblocked children in the local Markdown tracker."""

from pathlib import Path
import re
import sys


def fields(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing issue front matter")
    front = text.split("---", 2)[1]
    return dict(re.findall(r"^([a-z_]+):[ \t]*(.*)$", front, flags=re.MULTILINE))


def frontier(directory: Path, parent: str | None = None) -> list[str]:
    records = [(path, fields(path)) for path in sorted(directory.glob("[0-9]*.md"))]
    statuses = {record["id"].strip(): record["status"].split("#", 1)[0].strip() for _, record in records}
    ready = []
    for path, record in records:
        status = statuses[record["id"].strip()]
        if status not in {"open", "closed"}:
            raise ValueError(f"{path.name}: unsupported status {status!r}")
        issue_parent = record.get("parent", "").strip()
        if status != "open" or not issue_parent or record.get("assignee", "").strip():
            continue
        if parent is not None and issue_parent != parent:
            continue
        blockers = re.findall(r"\d+", record.get("blocked_by", "[]").split("#", 1)[0])
        if all(statuses.get(blocker) == "closed" for blocker in blockers):
            ready.append(f"{path.name}  {record.get('labels', '')}  {record.get('title', '')}")
    return ready


if __name__ == "__main__":
    try:
        for row in frontier(Path(__file__).resolve().parent, sys.argv[1] if len(sys.argv) > 1 else None):
            print(row)
    except (KeyError, ValueError) as error:
        sys.exit(str(error))
