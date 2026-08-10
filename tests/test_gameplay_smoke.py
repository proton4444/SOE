from scripts.gameplay_smoke import run_smoke


def test_small_gameplay_path_is_human_explainable(tmp_path):
    summary = run_smoke(tmp_path / "gameplay_smoke")

    assert summary["verdict"] == "PASS"
    assert summary["turns_completed"] == 3
    assert summary["warning_count"] == 0
    assert all(check["passed"] for check in summary["checks"])
    assert (tmp_path / "gameplay_smoke" / "GAMEPLAY_REPORT.md").exists()
