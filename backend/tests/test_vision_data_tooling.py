"""Regression tests for the dataset preparation/audit/leakage-check tooling
scaffold (backend/scripts/vision_data/). These exercise the tooling's LOGIC
against small synthetic placeholder fixtures checked into
tests/fixtures/vision_data_sample/ -- they do not validate any real external
PPE dataset (none has been downloaded/audited in this project; see
docs/adr/0002-vision-v2-roadmap.md).
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "vision_data"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "vision_data_sample"

sys.path.insert(0, str(SCRIPTS_DIR))

import audit_vision_data  # noqa: E402
import check_vision_leakage  # noqa: E402
import prepare_vision_data  # noqa: E402


@pytest.fixture
def manifest(tmp_path):
    class_mapping = prepare_vision_data.load_class_mapping(FIXTURE_DIR / "class_mapping.json")
    m = prepare_vision_data.prepare_dataset(FIXTURE_DIR / "dataset_a", class_mapping, None, FIXTURE_DIR)
    path = tmp_path / "dataset_a_manifest.json"
    path.write_text(json.dumps(m))
    return path, m


def test_prepare_with_no_input_dir_exits_zero(capsys):
    rc = prepare_vision_data.main(["--input-dir", "/does/not/exist"])
    assert rc == 0
    assert "nothing to prepare" in capsys.readouterr().out.lower()


def test_prepare_dry_run_self_test_produces_manifest(tmp_path, capsys):
    out_dir = tmp_path / "manifests"
    rc = prepare_vision_data.main(["--dry-run", "--output", str(out_dir)])
    assert rc == 0
    manifests = list(out_dir.glob("*_manifest.json"))
    assert len(manifests) == 1
    data = json.loads(manifests[0].read_text())
    assert data["image_count"] == 3
    assert data["annotation_box_count"] == 5  # img001: 2 boxes, img002: 1 valid box, img003: 2 boxes (copy of img001)
    assert data["invalid_annotation_count"] == 2  # img002's unknown-class-id line + out-of-range coordinate line


def test_prepare_applies_canonical_class_mapping(manifest):
    _, m = manifest
    assert set(m["canonical_class_list"]) == {"helmet", "no_helmet", "vest", "person"}
    assert m["class_mapping_applied"]["hardhat"] == "helmet"


def test_prepare_detects_invalid_boxes_and_unknown_class_ids(manifest):
    _, m = manifest
    img002 = next(r for r in m["images"] if r["relpath"].endswith("img002.jpg"))
    reasons = {line["reason"] for line in img002["invalid_annotation_lines"]}
    assert "unknown_class_id" in reasons
    assert "coordinate_out_of_range" in reasons


def test_prepare_records_exact_duplicate_image_hashes(manifest):
    _, m = manifest
    img001 = next(r for r in m["images"] if r["relpath"].endswith("img001.jpg"))
    img003 = next(r for r in m["images"] if r["relpath"].endswith("img003.jpg"))
    assert img001["sha256"] == img003["sha256"]


def test_audit_detects_exact_duplicates(manifest):
    manifest_path, _ = manifest
    report = audit_vision_data.audit_manifest(manifest_path, FIXTURE_DIR)
    assert len(report["exact_duplicate_groups"]) == 1
    dup_group = report["exact_duplicate_groups"][0]
    assert any(p.endswith("img001.jpg") for p in dup_group)
    assert any(p.endswith("img003.jpg") for p in dup_group)


def test_audit_reports_class_balance_and_missing_annotations(manifest):
    manifest_path, _ = manifest
    report = audit_vision_data.audit_manifest(manifest_path, FIXTURE_DIR)
    assert report["class_balance"]["helmet"] >= 1
    assert report["class_balance"]["vest"] >= 1
    # img002's only valid box is class 1 ("no-hardhat" -> "no_helmet"); the
    # unknown-class-id/out-of-range lines are excluded from class balance.
    assert report["images_missing_annotations"] == []


def test_audit_flags_corrupt_image(manifest, tmp_path):
    manifest_path, m = manifest
    # Point one relpath at a non-image file to exercise the corrupt-image branch.
    m["images"][0]["relpath"] = "not_an_image.txt"
    (tmp_path / "not_an_image.txt").write_text("not an image")
    manifest_path.write_text(json.dumps(m))
    report = audit_vision_data.audit_manifest(manifest_path, tmp_path)
    assert any("not_an_image.txt" in c for c in report["corrupt_images"])


def test_leakage_checker_passes_on_clean_splits(manifest):
    manifest_path, _ = manifest
    leaks = check_vision_leakage.check_leakage(manifest_path, FIXTURE_DIR / "splits_clean.json", FIXTURE_DIR)
    assert leaks == []


def test_leakage_checker_catches_deliberate_leak(manifest):
    """The exact-duplicate img001.jpg (train) / img003.jpg (val) pair in
    splits_leaky.json is a deliberate leak, proving the checker actually
    catches something rather than trivially passing everything."""
    manifest_path, _ = manifest
    leaks = check_vision_leakage.check_leakage(manifest_path, FIXTURE_DIR / "splits_leaky.json", FIXTURE_DIR)
    assert len(leaks) >= 1
    assert any(leak["type"] == "exact_duplicate_cross_split" for leak in leaks)


def test_leakage_checker_cli_exit_codes(manifest, capsys):
    manifest_path, _ = manifest
    rc_clean = check_vision_leakage.main(
        ["--manifest", str(manifest_path), "--splits", str(FIXTURE_DIR / "splits_clean.json"), "--dataset-root", str(FIXTURE_DIR)]
    )
    assert rc_clean == 0

    rc_leaky = check_vision_leakage.main(
        ["--manifest", str(manifest_path), "--splits", str(FIXTURE_DIR / "splits_leaky.json"), "--dataset-root", str(FIXTURE_DIR)]
    )
    assert rc_leaky == 1
