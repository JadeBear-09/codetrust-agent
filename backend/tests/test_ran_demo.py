from __future__ import annotations

from pathlib import Path

import pytest

from tnoc.ran_demo import DemoRunRequest, RanDemoService


@pytest.fixture
def service(tmp_path: Path) -> RanDemoService:
    return RanDemoService(output_root=tmp_path / "runs")


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_guard"),
    [
        ("normal", "VERIFIED", "PASS"),
        ("stale_telemetry", "BLOCKED", "BLOCK"),
        ("duplicate_request", "ALREADY_APPLIED", "PASS"),
        ("donor_deterioration", "ROLLED_BACK", "PASS"),
    ],
)
async def test_four_demo_outcomes_are_derived_from_scenario_inputs(
    service: RanDemoService,
    scenario: str,
    expected_status: str,
    expected_guard: str,
) -> None:
    result = await service.run(DemoRunRequest(scenario=scenario))

    assert result["status"] == expected_status
    assert result["guard"]["verdict"] == expected_guard
    assert result["simulation"]["production_network_access"] is False
    assert result["simulation"]["computed_snapshots"] == 5
    assert (service.output_root / result["run_id"] / "run.jsonl").exists()
    assert (service.output_root / result["run_id"] / "summary.json").exists()


async def test_stale_evidence_blocks_every_write(service: RanDemoService) -> None:
    result = await service.run(DemoRunRequest(scenario="stale_telemetry"))

    assert result["execution"]["mutations"] == 0
    assert any(
        check["code"] == "TELEMETRY_STALE" and not check["passed"]
        for check in result["guard"]["checks"]
    )


async def test_duplicate_is_safe_noop_after_verified_operation(service: RanDemoService) -> None:
    result = await service.run(DemoRunRequest(scenario="duplicate_request"))

    assert result["execution"]["duplicate_suppressed"] is True
    assert result["execution"]["mutations"] == 2
    assert result["audit"][-1]["event"] == "duplicate.suppressed"


async def test_donor_fault_rolls_back_and_verifies_restoration(service: RanDemoService) -> None:
    result = await service.run(DemoRunRequest(scenario="donor_deterioration"))

    assert result["execution"]["rollback_applied"] is True
    assert result["execution"]["rollback_verified"] is True
    assert result["network_states"][-1]["label"] == "Baseline restored"
    assert result["impact"]["stadium_prb_after_pct"] == result["impact"][
        "stadium_prb_before_pct"
    ]
