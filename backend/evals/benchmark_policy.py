from pathlib import Path
from statistics import median
from time import perf_counter_ns

from tnoc.domain import RemediationPlan, ToolAction
from tnoc.tools import ToolRegistry

SAMPLES = 2_000
CELLS = ["CELL-101", "CELL-102", "CELL-103"]


def build_plan() -> RemediationPlan:
    return RemediationPlan(
        summary="Bounded 15% traffic shift",
        risk="medium",
        actions=[
            ToolAction(
                tool_name="sandbox.shift_traffic",
                arguments={
                    "cell_ids": CELLS,
                    "shift_percent": 15,
                    "destination_cluster": "CLUSTER-BETA",
                },
                target_resource_ids=CELLS,
                expected_result="packet loss <= 2.0% and latency <= 95 ms",
                verification_tool_name="sandbox.verify_change",
                verification_arguments={"cell_ids": CELLS},
                rollback_tool_name="sandbox.rollback_traffic",
                rollback_arguments={"cell_ids": CELLS},
                rollback_verification_tool_name="sandbox.verify_rollback",
                rollback_verification_arguments={"cell_ids": CELLS},
            )
        ],
        blast_radius=CELLS,
        preconditions=["baseline captured", "neighbour capacity observed"],
        stop_conditions=["packet loss > 2.0%", "latency > 95 ms"],
        requires_approval=True,
    )


def run() -> None:
    registry = ToolRegistry(
        Path("config/tools.sandbox.json"),
        Path("config/policy.json"),
    )
    plan = build_plan()
    for _ in range(100):
        assert registry.evaluate(plan, set(CELLS)).allowed
    timings: list[float] = []
    for _ in range(SAMPLES):
        started = perf_counter_ns()
        decision = registry.evaluate(plan, set(CELLS))
        timings.append((perf_counter_ns() - started) / 1_000_000)
        assert decision.allowed and decision.requires_approval
    timings.sort()
    print(f"samples={SAMPLES}")
    print(f"median_ms={median(timings):.4f}")
    print(f"p95_ms={timings[int(SAMPLES * 0.95)]:.4f}")


if __name__ == "__main__":
    run()
