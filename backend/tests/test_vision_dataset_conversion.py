"""Regression test for the Industrial-Safety dataset class-index remap
(backend/scripts/vision_data/convert_industrial_safety_labels.py).

Fixture label lines below are real lines copied verbatim from the actual
extracted dataset (external-data/raw_dataset/train/labels/*.txt) during the
v1.2 vision experiment -- not synthetic placeholders. Source files:
  - construction-331-_jpg.rf.d278fa6154ec0080514e76b58c558906.txt
  - Twalv0995_jpg.rf.b97059f937b7f7deaaafed7c75928d0c.txt
  - 00014_jpg.rf.01f4b06258af718b566bbdeb8a84d70e.txt (contains a no_hardhat box)
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "vision_data"))

from convert_industrial_safety_labels import (  # noqa: E402
    CANONICAL_CLASSES,
    RAW_CLASSES,
    LabelConversionError,
    remap_label_line,
    remap_label_text,
)

# Real fixture lines, class id, expected canonical name
REAL_LINES = [
    ("2 0.8234375 0.56484375 0.353125 0.2515625", "person"),
    ("0 0.003125 0.6609375 0.00625 0.028125", "helmet"),
    ("2 0.015625 0.7171875 0.03125 0.146875", "person"),
    ("3 0.5578125 0.40234375 0.4328125 0.2421875", "vest"),
    ("1 0.31328125 0.3609375 0.06015625 0.0390625", "no_helmet"),
]

REAL_MULTILINE_LABEL_FILE = (
    "3 0.53203125 0.7109375 0.30390625 0.5421875\n"
    "0 0.53125 0.19140625 0.16796875 0.1796875\n"
    "3 0.315625 0.51484375 0.08828125 0.1828125\n"
    "1 0.31328125 0.3609375 0.06015625 0.0390625\n"
)


def test_canonical_class_order_matches_registry():
    # Must match models/registry.json ppe_detector.runtime_classes exactly.
    assert CANONICAL_CLASSES == ["person", "helmet", "vest", "no_helmet"]


def test_raw_classes_match_dataset_yaml():
    assert RAW_CLASSES == ["hardhat", "no_hardhat", "person", "safety_vest"]


@pytest.mark.parametrize("line,expected_name", REAL_LINES)
def test_remap_real_line_maps_to_expected_canonical_class(line, expected_name):
    converted = remap_label_line(line)
    converted_idx = int(converted.split()[0])
    assert CANONICAL_CLASSES[converted_idx] == expected_name
    # coordinates must be preserved byte-for-byte
    assert converted.split()[1:] == line.split()[1:]


def test_remap_real_multiline_label_file_preserves_box_count_and_order():
    converted = remap_label_text(REAL_MULTILINE_LABEL_FILE)
    converted_lines = converted.splitlines()
    original_lines = REAL_MULTILINE_LABEL_FILE.splitlines()
    assert len(converted_lines) == len(original_lines)

    expected_names = ["vest", "helmet", "vest", "no_helmet"]
    for converted_line, expected_name in zip(converted_lines, expected_names):
        idx = int(converted_line.split()[0])
        assert CANONICAL_CLASSES[idx] == expected_name


def test_remap_rejects_unknown_class_id():
    with pytest.raises(LabelConversionError):
        remap_label_line("4 0.5 0.5 0.1 0.1")


def test_remap_rejects_non_numeric_class_id():
    with pytest.raises(LabelConversionError):
        remap_label_line("no_hardhat 0.5 0.5 0.1 0.1")


def test_remap_preserves_empty_label_file():
    assert remap_label_text("") == ""


def test_no_vest_class_never_introduced():
    for line, _ in REAL_LINES:
        converted = remap_label_line(line)
        idx = int(converted.split()[0])
        assert CANONICAL_CLASSES[idx] != "no_vest"
    assert "no_vest" not in CANONICAL_CLASSES
