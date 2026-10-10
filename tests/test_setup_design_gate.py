"""The harness must not mistake functional evidence for visual approval."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_design_gate", ROOT / "scripts/check_setup_design.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def project(tmp_path):
    (tmp_path / gate.CONTRACT).parent.mkdir(parents=True)
    (tmp_path / gate.CONTRACT).write_bytes((ROOT / gate.CONTRACT).read_bytes())
    return tmp_path


def implemented(project):
    contract = gate.read_contract(project)
    contract["implementation_status"] = "implemented"
    (project / gate.CONTRACT).write_text(json.dumps(contract), encoding="utf-8")
    return contract


def review(project, contract):
    folder = project / "build/v2-validation/visual-test"
    folder.mkdir(parents=True)
    reference = project / contract["reference"]["local_path"]
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"reference fixture")
    contract["reference"]["sha256"] = hashlib.sha256(reference.read_bytes()).hexdigest()
    (project / gate.CONTRACT).write_text(json.dumps(contract), encoding="utf-8")
    matrix = contract["matrix"]
    captures = []
    for index, state in enumerate(contract["states"]):
        metadata = {axis: values[index % len(values)] for axis, values in matrix.items()}
        dpr = 2.5 if metadata["qt_scales"] == "windows-system" else float(metadata["qt_scales"])
        capture = folder / f"synthetic-{index}.png"
        size = tuple(round(value * dpr) for value in metadata["logical_sizes"])
        Image.new("RGB", size, (index * 19, 100, 100)).save(capture)
        captures.append({"path": str(capture.relative_to(project)), "sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
                         "state": state, "dpr": dpr, **metadata})
    record = {"contract_digest": gate.contract_digest(project), "source_digest": "source-v1",
              "reviewer": "Independent test reviewer", "independent": True,
              "checks": {c["id"]: "pass" for c in contract["manual_checks"]}, "screenshots": captures}
    (project / gate.REVIEW).write_text(json.dumps(record), encoding="utf-8")
    return record, capture


def save(project, record):
    (project / gate.REVIEW).write_text(json.dumps(record), encoding="utf-8")


def test_current_direction_never_inherits_old_approval(project):
    contract = gate.read_contract(project)
    assert contract["implementation_status"] == "pending"
    assert gate.review_status(project, contract, "source-v1")[0] == "PENDING"
    assert contract["states"]["empty"]["primary"] == "install_openmenu"
    assert contract["states"]["inaccessible"]["backup"] == "hidden"
    assert contract["states"]["readonly"]["primary"] == "inspect_destination"
    assert contract["states"]["security_blocked"]["primary"] == "choose_other_destination"


def test_missing_review_stays_pending(project):
    contract = implemented(project)
    assert gate.review_status(project, contract, "source-v1")[0] == "PENDING"


def test_matching_record_is_only_recorded_approval(project):
    contract = implemented(project)
    review(project, contract)
    assert gate.review_status(project, contract, "source-v1")[0] == "APPROVED"
    assert gate.review_status(project, contract, "source-v2")[0] == "PENDING"
    contract["id"] += "-changed"
    (project / gate.CONTRACT).write_text(json.dumps(contract), encoding="utf-8")
    assert gate.review_status(project, contract, "source-v1")[0] == "PENDING"


@pytest.mark.parametrize("defect", ["no_review", "not_independent", "failed", "missing_check", "no_images", "changed_image", "outside", "missing_state", "missing_theme", "malformed", "reused_image", "fake_png", "wrong_size", "reference_changed"])
def test_incomplete_or_changed_review_is_not_approved(project, defect):
    contract = implemented(project)
    record, capture = review(project, contract)
    if defect == "no_review": record["reviewer"] = ""
    elif defect == "not_independent": record["independent"] = False
    elif defect == "failed": record["checks"]["artwork"] = "fail"
    elif defect == "missing_check": record["checks"].pop("icons")
    elif defect == "no_images": record["screenshots"] = []
    elif defect == "changed_image": capture.write_bytes(b"different")
    elif defect == "outside": record["screenshots"][0]["path"] = "outside.png"
    elif defect == "missing_state": record["screenshots"].pop()
    elif defect == "missing_theme":
        for entry in record["screenshots"]: entry["themes"] = "light"
    elif defect == "reused_image":
        record["screenshots"][1]["path"] = record["screenshots"][0]["path"]
        record["screenshots"][1]["sha256"] = record["screenshots"][0]["sha256"]
    elif defect == "fake_png":
        capture.write_bytes(b"not PNG")
        record["screenshots"][-1]["sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
    elif defect == "wrong_size": record["screenshots"][0]["dpr"] = 3
    elif defect == "reference_changed": (project / contract["reference"]["local_path"]).write_bytes(b"modified")
    elif defect == "malformed": record = {"wrong": True}
    save(project, record)
    assert gate.review_status(project, contract, "source-v1")[0] == "PENDING"


def test_report_refresh_detects_staleness_and_preserves_review(project):
    contract = implemented(project)
    review(project, contract)
    before = (project / gate.REVIEW).read_bytes()
    assert gate.refresh(project, "source-v1")
    assert gate.refresh(project, "source-v1", check=True)
    assert not gate.refresh(project, "source-v2", check=True)
    assert (project / gate.REVIEW).read_bytes() == before
    assert "APPROVED" in (project / gate.REPORT).read_text(encoding="utf-8")
    template = json.loads((project / gate.TEMPLATE).read_text(encoding="utf-8"))
    assert template["independent"] is False
    assert set(template["checks"].values()) == {"pending"}


def test_visual_resource_bytes_invalidate_source_digest(tmp_path, monkeypatch):
    module_spec = importlib.util.spec_from_file_location("v2_validation_test", ROOT / "scripts/validate_v2.py")
    validator = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(validator)
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    monkeypatch.setattr(validator, "__file__", str(tmp_path / "scripts/validate_v2.py"))
    for relative in ["pyproject.toml", "scripts/validate_v2.py", "scripts/check_setup_design.py",
                     "docs/design/setup-direction.json", "docs/design/SETUP_DESIGN_DIRECTION.md"]:
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"fixture")
    artwork = tmp_path / "src/resources/setup.png"
    artwork.parent.mkdir(parents=True)
    before = validator.source_digest()
    artwork.write_bytes(b"raster-data\r\n")
    with_art = validator.source_digest()
    assert with_art != before
    artwork.write_bytes(b"raster-data\n")
    assert validator.source_digest() != with_art  # Raster bytes must not be normalized.
