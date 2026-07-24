import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.evidence import (
    strategy_logic_sha256,
    verify_evidence,
    verify_propr_paper_evidence,
)
from scripts.propr_contract import TRUSTED_PATHS


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_pair(root, spec, *, dsr=0.96, oos="PASS", checker="APPROVE_EVIDENCE_READY"):
    artifacts = root / "evidence" / "artifacts"
    manifests = root / "evidence" / "manifests"
    receipts = root / "evidence" / "checker"
    for path in (artifacts, manifests, receipts):
        path.mkdir(parents=True, exist_ok=True)
    dsr_path, oos_path = artifacts / "dsr.json", artifacts / "oos.json"
    dsr_path.write_text('{"metric":"dsr"}')
    oos_path.write_text('{"split":"holdout"}')
    manifest = {
        "schema_version": 1,
        "strategy_id": spec["id"],
        "strategy_logic_sha256": strategy_logic_sha256(spec),
        "maker_run_id": "maker-1",
        "dsr": {"value": dsr, "artifact_path": str(dsr_path.relative_to(root)),
                "artifact_sha256": _sha(dsr_path)},
        "oos": {"verdict": oos, "artifact_path": str(oos_path.relative_to(root)),
                "artifact_sha256": _sha(oos_path)},
    }
    manifest_path = manifests / f"{spec['id']}.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    receipt = {
        "schema_version": 1,
        "strategy_id": spec["id"],
        "maker_run_id": "maker-1",
        "checker_run_id": "checker-1",
        "manifest_sha256": _sha(manifest_path),
        "verdict": checker,
    }
    receipt_path = receipts / f"{spec['id']}.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True))
    return manifest_path, receipt_path


def _valid_propr_pair(root, spec, account_id, execution_contract):
    trusted = {}
    for relative in TRUSTED_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# frozen {relative}\n")
        trusted[relative] = path
    runner = trusted["scripts/propr_paper.py"]
    manifests = root / "evidence" / "propr" / "manifests"
    receipts = root / "evidence" / "propr" / "checker"
    for path in (manifests, receipts):
        path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "add", "--", *TRUSTED_PATHS], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "implementation"], cwd=root, check=True)
    implementation_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    manifest = {
        "schema_version": 1,
        "scope": "propr-free-trial-paper",
        "strategy_id": spec["id"],
        "strategy_logic_sha256": strategy_logic_sha256(spec),
        "implementation_commit": implementation_commit,
        "maker_run_id": "paper-maker-1",
        "paper_only": True,
        "account_id": account_id,
        "challenge_slug": "free-trial",
        "initial_balance": 5000,
        "trusted_artifacts": {
            relative: {
                "artifact_path": relative,
                "artifact_sha256": _sha(path),
            }
            for relative, path in trusted.items()
        },
        "execution_contract": execution_contract,
    }
    manifest_path = manifests / f"{spec['id']}.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    receipt = {
        "schema_version": 1,
        "scope": "propr-free-trial-paper",
        "strategy_id": spec["id"],
        "maker_run_id": "paper-maker-1",
        "checker_run_id": "paper-checker-1",
        "manifest_sha256": _sha(manifest_path),
        "verdict": "APPROVE_PROPR_PAPER_EXECUTION",
    }
    receipt_path = receipts / f"{spec['id']}.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True))
    return manifest_path, receipt_path, runner


def test_valid_independent_evidence_is_verified(tmp_path):
    spec = {"id": "alpha-v1", "status": "challenger", "signals": [{"name": "tsmom"}]}
    _valid_pair(tmp_path, spec)
    result = verify_evidence(spec, tmp_path)
    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["reasons"] == []


def test_missing_manifest_and_checker_fail_closed(tmp_path):
    result = verify_evidence({"id": "alpha-v1"}, tmp_path)
    assert result["verified"] is False
    assert result["reasons"] == ["manifest_missing", "checker_missing"]


def test_malformed_manifest_fails_closed(tmp_path):
    spec = {"id": "alpha-v1"}
    manifest, _ = _valid_pair(tmp_path, spec)
    manifest.write_text("{")
    result = verify_evidence(spec, tmp_path)
    assert result["verified"] is False
    assert "manifest_invalid_json" in result["reasons"]


def test_low_or_non_finite_dsr_is_blocked(tmp_path):
    spec = {"id": "alpha-v1", "status": "challenger"}
    _valid_pair(tmp_path, spec, dsr=0.94)
    assert "dsr_below_threshold" in verify_evidence(spec, tmp_path)["reasons"]
    _valid_pair(tmp_path, spec, dsr=float("nan"))
    assert "dsr_value_invalid" in verify_evidence(spec, tmp_path)["reasons"]
    _valid_pair(tmp_path, spec, dsr=1.01)
    assert "dsr_value_invalid" in verify_evidence(spec, tmp_path)["reasons"]


def test_oos_reject_or_artifact_tamper_is_blocked(tmp_path):
    spec = {"id": "alpha-v1", "status": "challenger"}
    _valid_pair(tmp_path, spec, oos="FAIL")
    assert "oos_not_pass" in verify_evidence(spec, tmp_path)["reasons"]
    _valid_pair(tmp_path, spec)
    (tmp_path / "evidence/artifacts/oos.json").write_text("tampered")
    assert "oos_artifact_hash_mismatch" in verify_evidence(spec, tmp_path)["reasons"]


def test_dsr_artifact_tamper_is_blocked(tmp_path):
    spec = {"id": "alpha-v1", "status": "challenger"}
    _valid_pair(tmp_path, spec)
    (tmp_path / "evidence/artifacts/dsr.json").write_text("tampered")
    assert "dsr_artifact_hash_mismatch" in verify_evidence(spec, tmp_path)["reasons"]


def test_checker_reject_same_run_or_manifest_tamper_is_blocked(tmp_path):
    spec = {"id": "alpha-v1", "status": "challenger"}
    manifest, receipt = _valid_pair(tmp_path, spec, checker="REJECT")
    assert "checker_not_approved" in verify_evidence(spec, tmp_path)["reasons"]
    checker_data = json.loads(receipt.read_text())
    checker_data.update(checker_run_id="maker-1", verdict="APPROVE_EVIDENCE_READY")
    receipt.write_text(json.dumps(checker_data))
    assert "checker_not_independent" in verify_evidence(spec, tmp_path)["reasons"]
    _valid_pair(tmp_path, spec)
    manifest.write_text(manifest.read_text() + "\n")
    assert "checker_manifest_hash_mismatch" in verify_evidence(spec, tmp_path)["reasons"]


def test_checker_independence_cannot_be_bypassed_with_whitespace(tmp_path):
    spec = {"id": "alpha-v1"}
    _, receipt = _valid_pair(tmp_path, spec)
    checker = json.loads(receipt.read_text())
    checker["checker_run_id"] = " maker-1 "
    receipt.write_text(json.dumps(checker))
    result = verify_evidence(spec, tmp_path)
    assert result["verified"] is False
    assert "checker_run_id_invalid" in result["reasons"]


def test_logic_mutation_invalidates_but_status_change_does_not(tmp_path):
    spec = {"id": "alpha-v1", "status": "challenger", "entry": {"rule": "A"}}
    _valid_pair(tmp_path, spec)
    changed_status = {**spec, "status": "champion"}
    assert verify_evidence(changed_status, tmp_path)["verified"] is True
    changed_logic = {**spec, "entry": {"rule": "B"}}
    assert "strategy_logic_hash_mismatch" in verify_evidence(changed_logic, tmp_path)["reasons"]


def test_artifact_path_cannot_escape_repo(tmp_path):
    spec = {"id": "alpha-v1"}
    manifest, _ = _valid_pair(tmp_path, spec)
    data = json.loads(manifest.read_text())
    data["dsr"]["artifact_path"] = "../outside.json"
    manifest.write_text(json.dumps(data))
    assert "dsr_artifact_outside_repo" in verify_evidence(spec, tmp_path)["reasons"]


def test_valid_propr_paper_execution_pair_is_verified(tmp_path):
    spec = {"id": "alpha-v1", "status": "champion", "engine": "portfolio"}
    account_id = "urn:prp-account:paper-1"
    contract = {"gross_override": 0.3, "max_leverage": 2}
    _valid_propr_pair(tmp_path, spec, account_id, contract)

    result = verify_propr_paper_evidence(
        spec, tmp_path, account_id=account_id, execution_contract=contract)

    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["scope"] == "propr-free-trial-paper"


def test_propr_trusted_paths_close_local_imports_and_detect_tamper(tmp_path):
    required = {
        "backtest/__init__.py",
        "backtest/engine.py",
        "backtest/risk.py",
        "backtest/signals.py",
        "backtest/lifecycle.py",
        "pipeline/__init__.py",
        "scripts/__init__.py",
        "scripts/paper_trade.py",
        "scripts/runtime_health.py",
    }
    assert required.issubset(TRUSTED_PATHS)
    spec = {"id": "alpha-v1", "status": "champion", "engine": "portfolio"}
    account_id = "urn:prp-account:paper-1"
    contract = {"gross_override": 0.3}
    _valid_propr_pair(tmp_path, spec, account_id, contract)

    for relative in sorted(required):
        path = tmp_path / relative
        original = path.read_text()
        path.write_text(original + "# tampered\n")
        result = verify_propr_paper_evidence(
            spec, tmp_path, account_id=account_id,
            execution_contract=contract)
        assert any(reason.endswith("_artifact_hash_mismatch")
                   for reason in result["reasons"]), relative
        path.write_text(original)


def test_propr_paper_pair_binds_account_runner_and_overlay(tmp_path):
    spec = {"id": "alpha-v1", "status": "champion", "engine": "portfolio"}
    account_id = "urn:prp-account:paper-1"
    contract = {"gross_override": 0.3, "max_leverage": 2}
    _, _, runner = _valid_propr_pair(tmp_path, spec, account_id, contract)

    wrong_account = verify_propr_paper_evidence(
        spec, tmp_path, account_id="urn:prp-account:other",
        execution_contract=contract)
    assert "paper_account_id_mismatch" in wrong_account["reasons"]

    wrong_overlay = verify_propr_paper_evidence(
        spec, tmp_path, account_id=account_id,
        execution_contract={**contract, "gross_override": 1.0})
    assert "paper_execution_contract_mismatch" in wrong_overlay["reasons"]

    runner.write_text("# changed paper runner\n")
    tampered = verify_propr_paper_evidence(
        spec, tmp_path, account_id=account_id, execution_contract=contract)
    assert any(reason.endswith("_artifact_hash_mismatch")
               for reason in tampered["reasons"])


def test_propr_implementation_commit_must_be_an_ancestor(tmp_path):
    spec = {"id": "alpha-v1", "status": "champion", "engine": "portfolio"}
    account_id = "urn:prp-account:paper-1"
    contract = {"gross_override": 0.3}
    manifest_path, receipt_path, _ = _valid_propr_pair(
        tmp_path, spec, account_id, contract)
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    unrelated = subprocess.run(
        ["git", "commit-tree", tree], cwd=tmp_path, check=True,
        input="unrelated implementation\n", capture_output=True, text=True,
    ).stdout.strip()
    manifest = json.loads(manifest_path.read_text())
    manifest["implementation_commit"] = unrelated
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    receipt = json.loads(receipt_path.read_text())
    receipt["manifest_sha256"] = _sha(manifest_path)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True))

    result = verify_propr_paper_evidence(
        spec, tmp_path, account_id=account_id, execution_contract=contract)

    assert "paper_implementation_commit_mismatch" in result["reasons"]
