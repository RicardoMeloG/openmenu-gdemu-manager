"""Generate a separate, evidence-bound setup design gate; never auto-approve UX."""
import argparse
import hashlib
import json
import math

from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("docs/design/setup-direction.json")
REPORT = Path("docs/SETUP_DESIGN_VALIDATION.md")
REVIEW = Path("build/v2-validation/setup-design-review.json")
TEMPLATE = Path("build/v2-validation/setup-design-review.template.json")


def read_contract(root=ROOT):
    contract = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    required = {"unselected", "checking", "empty", "ready", "readonly", "inaccessible",
                "security_blocked", "backup_running", "backup_failed", "install_running",
                "install_failed", "installed"}
    if contract.get("schema_version") != 1 or set(contract["states"]) != required:
        raise ValueError("Unsupported or incomplete setup design contract")
    if contract["implementation_status"] not in {"pending", "implemented"}:
        raise ValueError("Invalid implementation status")
    ids = [item["id"] for item in contract["manual_checks"]]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Missing or duplicated manual criteria")
    return contract


def contract_digest(root=ROOT):
    return hashlib.sha256((root / CONTRACT).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def review_status(root, contract, source_digest):
    """Approval is a recorded human attestation, not an automatic visual verdict."""
    if contract["implementation_status"] != "implemented":
        return "PENDING", "Qt adaptation not implemented for this direction."
    path = root / REVIEW
    if not path.is_file():
        return "PENDING", "Independent visual review not recorded."
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["contract_digest"] != contract_digest(root) or record["source_digest"] != source_digest:
            return "PENDING", "Review is stale: source or design contract changed."
        if not record["reviewer"].strip() or record["independent"] is not True:
            return "PENDING", "Named independent reviewer is required."
        ids = {check["id"] for check in contract["manual_checks"]}
        if set(record["checks"]) != ids or any(value != "pass" for value in record["checks"].values()):
            return "PENDING", "Manual criteria remain pending or failed."
        reference = (root / contract["reference"]["local_path"]).resolve()
        if not reference.is_relative_to(root.resolve()) or hashlib.sha256(reference.read_bytes()).hexdigest() != contract["reference"]["sha256"]:
            return "PENDING", "Accepted reference is missing or changed."
        evidence = record["screenshots"]
        if not evidence:
            return "PENDING", "Screenshot evidence is required."
        capture_root = (root / "build/v2-validation").resolve()
        seen_paths, seen_hashes = set(), set()
        for entry in evidence:
            relative = Path(entry["path"])
            file = (root / relative).resolve()
            if relative.is_absolute() or not file.is_relative_to(capture_root) or file.suffix.lower() != ".png":
                return "PENDING", "Screenshot must be a local validation PNG."
            if file in seen_paths or entry["sha256"] in seen_hashes:
                return "PENDING", "Each matrix sample needs a distinct screenshot; relabeling one image is not evidence."
            seen_paths.add(file)
            seen_hashes.add(entry["sha256"])
            if file.stat().st_size > 20 * 1024 * 1024:
                return "PENDING", "Screenshot exceeds the evidence size bound."
            if hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
                return "PENDING", "Screenshot evidence changed after review."
            if entry["state"] not in contract["states"]:
                return "PENDING", "Unknown screenshot state."
            for axis in ("languages", "themes", "qt_scales", "disclosure"):
                if entry[axis] not in contract["matrix"][axis]:
                    return "PENDING", "Invalid screenshot matrix metadata."
            if entry["logical_sizes"] not in contract["matrix"]["logical_sizes"]:
                return "PENDING", "Invalid screenshot size."
            dpr = float(entry["dpr"])
            if not math.isfinite(dpr) or not 0.5 <= dpr <= 4:
                return "PENDING", "Invalid screenshot DPR."
            if entry["qt_scales"] != "windows-system" and abs(dpr - float(entry["qt_scales"])) > 0.01:
                return "PENDING", "Screenshot DPR differs from its scale metadata."
            with Image.open(file) as image:
                if image.format != "PNG" or any(abs(actual - logical * dpr) > 1 for actual, logical in zip(image.size, entry["logical_sizes"])):
                    return "PENDING", "PNG dimensions do not match the recorded logical size and DPR."
                image.verify()
        if {e["state"] for e in evidence} != set(contract["states"]):
            return "PENDING", "Some setup states lack reviewed screenshots."
        for axis, values in contract["matrix"].items():
            if {json.dumps(e[axis]) for e in evidence} != {json.dumps(v) for v in values}:
                return "PENDING", "Some matrix values lack reviewed screenshots."
        return "APPROVED", "Independent review recorded for matching sources and screenshots."
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "PENDING", "Review evidence is missing, malformed or unreadable."


def report_text(root, contract, source_digest):
    status, reason = review_status(root, contract, source_digest)
    lines = ["# Setup design validation", "", "Generated by `scripts/check_setup_design.py`; do not edit results manually.",
             "", f"Design contract: `{contract['id']}`", f"Contract digest: `{contract_digest(root)}`",
             f"Source digest: `{source_digest}`", "", f"Design result: **{status}**", "", reason,
             "", "Functional pytest PASS is separate from this design gate. Earlier compact-wizard approvals do not approve the new reference.",
             "", "| Criterion | Required review |", "| --- | --- |"]
    lines += [f"| {item['id']} | {item['criterion']} |" for item in contract["manual_checks"]]
    lines += ["", "Coverage requires every state and every language/theme/size/scale/disclosure value; this is axis coverage, not exhaustive Cartesian coverage.",
              "The reviewer must inspect rendered screenshots and interactions; PNG format, unique captures and dimension checks prevent basic evidence substitution; the reviewer still judges image content and interaction. Filenames and metadata alone do not certify visual quality.",
              "", "The supplied composition reference is retained locally with its hash in the contract; it is not an application asset or an automatically approved baseline.",
              "Human acceptance, clean Windows and Dreamcast/physical SD checks remain separate.", ""]
    return "\n".join(lines)


def refresh(root, source_digest, check=False):
    contract = read_contract(root)
    expected = report_text(root, contract, source_digest)
    if check:
        return (root / REPORT).is_file() and (root / REPORT).read_text(encoding="utf-8") == expected
    (root / REPORT).write_text(expected, encoding="utf-8")
    template = {"contract_digest": contract_digest(root), "source_digest": source_digest,
                "reviewer": "", "independent": False,
                "checks": {item["id"]: "pending" for item in contract["manual_checks"]}, "screenshots": []}
    (root / TEMPLATE).parent.mkdir(parents=True, exist_ok=True)
    (root / TEMPLATE).write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main():
    from validate_v2 import source_digest
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-docs", action="store_true")
    parser.add_argument("--require-approval", action="store_true")
    args = parser.parse_args()
    digest = source_digest()
    if not refresh(ROOT, digest, check=args.check_docs):
        print("Setup design documentation is stale. Run python scripts/check_setup_design.py.")
        return 1
    status, reason = review_status(ROOT, read_contract(), digest)
    print(f"Setup design: {status}. {reason}")
    return 1 if args.require_approval and status != "APPROVED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
