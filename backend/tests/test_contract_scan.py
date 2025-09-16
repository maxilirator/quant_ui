from pathlib import Path
from app.data.contract import (
    scan_curated_root,
    summarize,
    PartitionIssue,
    REQUIRED_DOMAINS,
)


def test_missing_root(tmp_path: Path):
    root = tmp_path / "does_not_exist"
    issues = scan_curated_root(root)
    assert any(i.kind == "missing_root" for i in issues)


def test_missing_domains(tmp_path: Path):
    # Create curated root but no domains
    issues = scan_curated_root(tmp_path)
    missing = {i.domain for i in issues if i.kind == "missing_domain"}
    for dom in REQUIRED_DOMAINS:
        assert dom in missing


def test_plain_directory_detection(tmp_path: Path):
    bars = tmp_path / "bars_eod"
    bars.mkdir()
    (bars / "ERIC").mkdir()
    issues = scan_curated_root(tmp_path)
    assert any(
        i.domain == "bars_eod" and i.kind == "unexpected_plain_dir" for i in issues
    )


def test_key_value_partition_ok(tmp_path: Path):
    fx = tmp_path / "fx_rates"
    fx.mkdir()
    (fx / "ccy_pair=EURSEK").mkdir()
    issues = scan_curated_root(tmp_path)
    # Only other required domains will be missing
    assert not any(
        i.domain == "fx_rates" and i.kind == "unexpected_plain_dir" for i in issues
    )
