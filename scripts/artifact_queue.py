"""Select GitHub Actions artifacts for FIFO, idempotent workflow queues.

The helper is intentionally stdlib-only.  Workflows fetch the complete paginated
artifact inventory, while this module performs deterministic filtering and
ordering without truncating the queue.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def _flatten(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _flatten(item)
    elif isinstance(value, dict) and isinstance(value.get("artifacts"), list):
        yield from _flatten(value["artifacts"])
    elif isinstance(value, dict):
        yield value


def load_artifacts(path: str | Path) -> list[dict[str, Any]]:
    """Read a GitHub API response, paginated response array, or JSONL stream."""
    raw = Path(path).read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return list(_flatten(value))


def _on_branch(artifact: dict[str, Any], branch: str) -> bool:
    run = artifact.get("workflow_run")
    return (
        artifact.get("expired") is False
        and isinstance(run, dict)
        and run.get("head_branch") == branch
        and isinstance(artifact.get("id"), int)
        and isinstance(artifact.get("name"), str)
        and isinstance(artifact.get("created_at"), str)
    )


def _deduplicate(artifacts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if isinstance(artifact_id, int):
            by_id[artifact_id] = artifact
    return list(by_id.values())


def candidate_ids(
    artifacts: Iterable[dict[str, Any]],
    *,
    source_prefix: str,
    branch: str = "main",
) -> list[int]:
    """Return every eligible source artifact id, oldest first.

    Marker artifacts are intentionally not considered here: their producer
    authority cannot be established from the artifact inventory alone.  Each
    workflow must verify the marker's producer run before treating a source as
    processed.
    """
    eligible = [item for item in _deduplicate(artifacts) if _on_branch(item, branch)]
    sources = [
        item
        for item in eligible
        if item["name"].startswith(source_prefix)
    ]
    sources.sort(key=lambda item: (item["created_at"], item["id"]))
    return [item["id"] for item in sources]


def marker_ids(
    artifacts: Iterable[dict[str, Any]], *, name: str, branch: str = "main"
) -> list[int]:
    """Return all non-expired marker ids with an exact name, oldest first."""
    markers = [
        item
        for item in _deduplicate(artifacts)
        if _on_branch(item, branch) and item["name"] == name
    ]
    markers.sort(key=lambda item: (item["created_at"], item["id"]))
    return [item["id"] for item in markers]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    candidates = commands.add_parser("candidates")
    candidates.add_argument("--artifacts", required=True)
    candidates.add_argument("--source-prefix", required=True)
    candidates.add_argument("--branch", default="main")

    markers = commands.add_parser("markers")
    markers.add_argument("--artifacts", required=True)
    markers.add_argument("--name", required=True)
    markers.add_argument("--branch", default="main")

    args = parser.parse_args()
    artifacts = load_artifacts(args.artifacts)
    ids = (
        candidate_ids(
            artifacts,
            source_prefix=args.source_prefix,
            branch=args.branch,
        )
        if args.command == "candidates"
        else marker_ids(artifacts, name=args.name, branch=args.branch)
    )
    for artifact_id in ids:
        print(artifact_id)


if __name__ == "__main__":
    main()
