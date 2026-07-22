import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import artifact_queue


def _artifact(artifact_id, name, created_at, *, branch="main", expired=False):
    return {
        "id": artifact_id,
        "name": name,
        "created_at": created_at,
        "expired": expired,
        "workflow_run": {"head_branch": branch},
    }


def test_candidates_include_sources_even_when_same_name_marker_exists():
    artifacts = []
    for index in range(60):
        key = f"{index:064x}"
        artifacts.extend([
            _artifact(index + 1, f"research-checker-{key}", f"2026-07-01T00:{index:02d}:00Z"),
            _artifact(index + 101, f"evolution-intake-{key}", f"2026-07-02T00:{index:02d}:00Z"),
        ])
    pending_key = "f" * 64
    artifacts.append(
        _artifact(999, f"research-checker-{pending_key}", "2026-07-03T00:00:00Z")
    )

    assert artifact_queue.candidate_ids(
        artifacts,
        source_prefix="research-checker-",
    ) == [*range(1, 61), 999]


def test_candidates_are_fifo_and_ignore_expired_or_non_main_artifacts():
    artifacts = [
        _artifact(3, "research-maker-new", "2026-07-03T00:00:00Z"),
        _artifact(1, "research-maker-old", "2026-07-01T00:00:00Z"),
        _artifact(2, "research-maker-feature", "2026-06-30T00:00:00Z", branch="feature"),
        _artifact(4, "research-maker-expired", "2026-06-29T00:00:00Z", expired=True),
    ]

    assert artifact_queue.candidate_ids(
        artifacts, source_prefix="research-maker-"
    ) == [1, 3]


def test_paginated_json_and_cli_return_every_pending_id(tmp_path):
    sources = [
        _artifact(index, f"research-checker-{index:064x}", f"2026-07-{index:02d}T00:00:00Z")
        for index in range(1, 4)
    ]
    payload = [{"artifacts": sources[:2]}, {"artifacts": sources[2:]}]
    inventory = tmp_path / "artifacts.json"
    inventory.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.artifact_queue",
            "candidates",
            "--artifacts",
            str(inventory),
            "--source-prefix",
            "research-checker-",
        ],
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["1", "2", "3"]


def test_marker_lookup_requires_exact_name_and_main():
    artifacts = [
        _artifact(1, "research-checker-pack", "2026-07-01T00:00:00Z"),
        _artifact(2, "research-checker-pack-extra", "2026-07-02T00:00:00Z"),
        _artifact(3, "research-checker-pack", "2026-07-03T00:00:00Z", branch="feature"),
    ]

    assert artifact_queue.marker_ids(artifacts, name="research-checker-pack") == [1]


def test_final_markers_cannot_prefilter_intake_sources():
    artifacts = []
    for index in range(60):
        key = f"{index:064x}"
        artifacts.extend([
            _artifact(index + 1, f"evolution-intake-{key}", f"2026-07-01T00:{index:02d}:00Z"),
            _artifact(index + 101, f"evolution-final-{key}", f"2026-07-02T00:{index:02d}:00Z"),
        ])
    pending_key = "e" * 64
    artifacts.append(
        _artifact(999, f"evolution-intake-{pending_key}", "2026-07-03T00:00:00Z")
    )

    assert artifact_queue.candidate_ids(
        artifacts,
        source_prefix="evolution-intake-",
    ) == [*range(1, 61), 999]


def test_candidates_cli_rejects_removed_unverified_marker_prefilter(tmp_path):
    inventory = tmp_path / "artifacts.json"
    inventory.write_text("[]", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.artifact_queue",
            "candidates",
            "--artifacts",
            str(inventory),
            "--source-prefix",
            "research-checker-",
            "--marker-prefix",
            "evolution-intake-",
        ],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --marker-prefix" in result.stderr


def test_evolution_queues_verify_marker_producers_before_skipping_sources():
    root = Path(__file__).resolve().parent.parent
    intake = (root / ".github/workflows/evolution-intake.yml").read_text(
        encoding="utf-8"
    )
    runner = (root / ".github/workflows/evolution-run.yml").read_text(
        encoding="utf-8"
    )

    for workflow in (intake, runner):
        assert "--marker-prefix" not in workflow
        assert workflow.index("--source-prefix") < workflow.index(
            'for artifact_id in "${candidates[@]}"'
        )

    assert '--name "evolution-intake-${name_pack_id}"' in intake
    assert '".github/workflows/evolution-intake.yml"' in intake
    assert '"$(jq -r \'.head_branch\' <<< "$disposition_run")" = "main"' in intake
    assert '"$(jq -r \'.conclusion\' <<< "$disposition_run")" = "success"' in intake

    assert '--name "evolution-final-${name_pack_id}"' in runner
    assert '".github/workflows/evolution-run.yml"' in runner
    assert '"$(jq -r \'.head_branch\' <<< "$final_run")" = "main"' in runner
    assert '"$(jq -r \'.conclusion\' <<< "$final_run")" = "success"' in runner


def test_research_workflow_dispatch_is_main_only_before_secret_steps():
    root = Path(__file__).resolve().parent.parent
    for name, job in (("research-maker.yml", "maker"), ("research-checker.yml", "checker")):
        workflow = (root / ".github/workflows" / name).read_text(encoding="utf-8")
        job_start = workflow.index(f"  {job}:\n")
        main_guard = workflow.index("    if: github.ref == 'refs/heads/main'", job_start)
        secret_step = workflow.index("${{ secrets.", job_start)

        assert job_start < main_guard < secret_step


def test_daily_maker_dedup_requires_authoritative_successful_producer():
    root = Path(__file__).resolve().parent.parent
    workflow = (root / ".github/workflows/research-maker.yml").read_text(encoding="utf-8")

    marker_lookup = workflow.index('python scripts/artifact_queue.py markers')
    producer_loop = workflow.index('for artifact_id in "${existing_ids[@]}"')
    no_op = workflow.index('echo "should_run=false"')

    assert marker_lookup < producer_loop < no_op
    assert '".github/workflows/research-maker.yml"' in workflow
    assert '"$(jq -r \'.head_branch\' <<< "$producer")" = "main"' in workflow
    assert '"$(jq -r \'.conclusion\' <<< "$producer")" = "success"' in workflow


def test_evolution_workflow_reuses_authoritative_stages_and_never_pushes():
    root = Path(__file__).resolve().parent.parent
    workflow = (root / ".github/workflows/evolution-run.yml").read_text(encoding="utf-8")

    assert workflow.count("scripts.evolution_cloud openrouter-maker") == 1
    assert workflow.count("scripts.evolution_cloud openrouter-checker") == 1
    assert '--name "evolution-maker-${PACK_ID}"' in workflow
    assert '--name "evolution-checker-${PACK_ID}"' in workflow
    assert "riusa i byte esatti del Maker precedente" in workflow
    assert "riusa i byte esatti del Checker precedente" in workflow
    assert "repo_commit: ${{ steps.stage.outputs.repo_commit }}" in workflow
    assert "ref: ${{ needs.maker.outputs.repo_commit }}" in workflow
    assert 'git rev-parse HEAD)" = "$MAKER_REPO_COMMIT"' in workflow
    assert "steps.resolve.outputs.reuse != 'true'" in workflow
    assert "actions/artifacts/${ARTIFACT_ID}/zip" in workflow
    assert workflow.count("OPENROUTER_API_KEY:") == 2
    assert workflow.count("openrouter:deepseek/deepseek-v4-pro") == 2
    assert "ZAI_API_KEY" not in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "git push" not in workflow
    assert "gh pr" not in workflow
    assert "HUMAN_PR_REQUIRED" in workflow
    assert "scripts.evolution_cloud validate-published" in workflow
    assert "--require-current-admission" in workflow

    integrity = (root / ".github/workflows/integrity-ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 2" in integrity
    assert "scripts.evolution_cloud validate-changed-admissions" in integrity
    assert "--base-ref HEAD^" in integrity


def test_manual_evolution_canary_is_branch_only_and_non_authoritative():
    root = Path(__file__).resolve().parent.parent
    workflow = (root / ".github/workflows/research-maker.yml").read_text(encoding="utf-8")
    canary = workflow.split("  evolution-canary:\n", 1)[1]

    assert "github.ref == 'refs/heads/main' && inputs.evolution_canary != true" in workflow
    assert "startsWith(github.ref, 'refs/heads/agent/evolution-canary-')" in canary
    assert "group: evolution-canary-${{ github.ref }}" in canary
    assert canary.count("OPENROUTER_API_KEY:") == 2
    assert "scripts.evolution_cloud openrouter-maker" in canary
    assert "scripts.evolution_cloud openrouter-checker" in canary
    assert "evolution-canary-${{ github.run_id }}" in canary
    assert "retention-days: 1" in canary
    assert '"CANARY.json"' in canary
    assert "scripts.evolution_cloud publish" not in canary
    assert "git push" not in canary
    assert "gh pr" not in canary
    assert "paper/" not in canary
