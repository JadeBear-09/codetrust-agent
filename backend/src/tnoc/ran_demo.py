from __future__ import annotations

import hashlib
import json
import math
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import orjson
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tnoc.model_runtime import RunLedger

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = BACKEND_ROOT / "config/ran-demo.json"
DEFAULT_EVENT_PATH = BACKEND_ROOT / "examples/events/stadium-event-fallback.json"
DEFAULT_OUTPUT_ROOT = BACKEND_ROOT.parent / "outputs/ran-demo"
TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"


class EventSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str
    country_code: str = Field(min_length=2, max_length=2)
    classification_name: str
    size: int = Field(gt=0, le=50)
    default_venue_capacity: int = Field(gt=0)
    expected_occupancy: float = Field(gt=0, le=1)


class ArrivalPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_minute: int
    fraction: float = Field(ge=0, le=1)


class TrafficSpike(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_minute: int
    width_minutes: int = Field(gt=0)
    multiplier: float = Field(ge=1)


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    clock_ratio: int = Field(gt=0)
    connected_user_ratio: float = Field(gt=0, le=1)
    average_user_demand_mbps: float = Field(gt=0)
    device_limit_mbps: float = Field(gt=0)
    base_latency_ms: float = Field(gt=0)
    congestion_soft_start_pct: float = Field(gt=0, lt=100)
    snapshot_minutes: list[int] = Field(min_length=2)
    arrival_curve: list[ArrivalPoint] = Field(min_length=2)
    traffic_spikes: list[TrafficSpike] = Field(default_factory=list)


class CellConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str = Field(pattern=r"^CELL-[A-Z0-9-]+$")
    label: str
    site_id: str
    latitude_offset: float
    longitude_offset: float
    radio_capacity_mbps: float = Field(gt=0)
    backhaul_capacity_mbps: float = Field(gt=0)
    baseline_users: int = Field(ge=0)
    event_share: float = Field(ge=0, le=1)
    base_handover_success_pct: float = Field(ge=0, le=100)
    base_drop_rate_pct: float = Field(ge=0, le=100)
    software_version: str
    config_version: int = Field(gt=0)


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry_max_age_seconds: int = Field(gt=0)
    congestion_threshold_pct: float = Field(gt=0, le=100)
    sustained_window_points: int = Field(gt=0)
    donor_prb_limit_pct: float = Field(gt=0, le=100)
    target_prb_pct: float = Field(gt=0, le=100)
    minimum_offload_pct: int = Field(gt=0, le=100)
    maximum_offload_pct: int = Field(gt=0, le=100)
    canary_pct: int = Field(gt=0, le=100)
    minimum_handover_success_pct: float = Field(ge=0, le=100)
    maximum_session_drop_rate_pct: float = Field(ge=0, le=100)
    maximum_latency_p95_ms: float = Field(gt=0)
    change_window_open: bool


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    label: str
    description: str
    faults: dict[str, float | bool] = Field(default_factory=dict)


class RanDemoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(gt=0)
    event_search: EventSearchConfig
    simulation: SimulationConfig
    cells: list[CellConfig] = Field(min_length=3)
    policy: PolicyConfig
    scenarios: list[ScenarioConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_topology(self) -> RanDemoConfig:
        cell_ids = [cell.cell_id for cell in self.cells]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("Cell IDs must be unique")
        if not math.isclose(sum(cell.event_share for cell in self.cells), 1.0, abs_tol=0.001):
            raise ValueError("Cell event shares must sum to one")
        if self.policy.canary_pct > self.policy.maximum_offload_pct:
            raise ValueError("Canary percentage exceeds maximum offload")
        if self.policy.minimum_offload_pct > self.policy.maximum_offload_pct:
            raise ValueError("Minimum offload exceeds maximum offload")
        points = [point.relative_minute for point in self.simulation.arrival_curve]
        if points != sorted(points) or len(points) != len(set(points)):
            raise ValueError("Arrival curve minutes must be unique and sorted")
        scenario_ids = [scenario.id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Scenario IDs must be unique")
        return self


class Venue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    latitude: float
    longitude: float


class PublicEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    name: str
    type: str
    venue: Venue
    starts_at: datetime
    ends_at: datetime
    estimated_attendance: int = Field(gt=0)
    attendance_confidence: float = Field(ge=0, le=1)
    attendance_basis: str
    source: str
    source_retrieved_at: datetime
    live: bool


class DemoRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(default="normal", pattern=r"^[a-z][a-z0-9_]{2,63}$")


def _read_env(name: str) -> str | None:
    direct = os.environ.get(name)
    if direct:
        return direct
    path = Path(".env")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            normalized = value.strip().strip("'\"")
            return normalized or None
    return None


class TicketmasterEventAdapter:
    """Fetches public event context and falls back to an explicit cached fixture."""

    def __init__(
        self,
        config: RanDemoConfig,
        *,
        fallback_path: Path,
        cache_path: Path,
    ) -> None:
        self.config = config
        self.fallback_path = fallback_path
        self.cache_path = cache_path

    @property
    def live_available(self) -> bool:
        return bool(_read_env("TICKETMASTER_API_KEY"))

    async def get_event(self) -> PublicEvent:
        mode = (_read_env("RAN_DEMO_EVENT_MODE") or "auto").casefold()
        if mode not in {"auto", "live", "cache"}:
            raise ValueError("RAN_DEMO_EVENT_MODE must be auto, live, or cache")
        if mode != "cache" and self.live_available:
            event = await self._fetch_live()
            if event is not None:
                self._store_cache(event)
                return event
            if mode == "live":
                raise RuntimeError(
                    "Ticketmaster event lookup failed; use auto mode for cache fallback"
                )
        cached = self._read_cache()
        if cached is not None:
            return cached
        return PublicEvent.model_validate_json(self.fallback_path.read_text(encoding="utf-8"))

    async def _fetch_live(self) -> PublicEvent | None:
        api_key = _read_env("TICKETMASTER_API_KEY")
        if not api_key:
            return None
        search = self.config.event_search
        params = {
            "apikey": api_key,
            "keyword": _read_env("TICKETMASTER_KEYWORD") or search.keyword,
            "countryCode": _read_env("TICKETMASTER_COUNTRY_CODE") or search.country_code,
            "classificationName": search.classification_name,
            "size": str(search.size),
            "sort": "date,asc",
            "locale": "*",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
                response = await client.get(TICKETMASTER_URL, params=params)
                response.raise_for_status()
            events = response.json().get("_embedded", {}).get("events", [])
            for payload in events:
                normalized = self._normalize(payload)
                if normalized is not None:
                    return normalized
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError):
            return None
        return None

    def _normalize(self, payload: dict[str, Any]) -> PublicEvent | None:
        venues = payload.get("_embedded", {}).get("venues", [])
        if not venues:
            return None
        venue = venues[0]
        location = venue.get("location") or {}
        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
            starts_at = self._event_datetime(payload.get("dates", {}), venue)
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            return None
        classifications = payload.get("classifications") or []
        classification = classifications[0] if classifications else {}
        event_type = (
            classification.get("genre", {}).get("name")
            or classification.get("segment", {}).get("name")
            or "public_event"
        )
        search = self.config.event_search
        attendance = round(search.default_venue_capacity * search.expected_occupancy)
        return PublicEvent(
            event_id=str(payload.get("id") or "ticketmaster-event"),
            name=str(payload.get("name") or "Public event"),
            type=str(event_type).casefold().replace(" ", "_"),
            venue=Venue(
                name=str(venue.get("name") or "Ticketmaster venue"),
                latitude=latitude,
                longitude=longitude,
            ),
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            estimated_attendance=attendance,
            attendance_confidence=0.68,
            attendance_basis="Configured venue capacity × expected occupancy",
            source="ticketmaster",
            source_retrieved_at=datetime.now(UTC),
            live=True,
        )

    @staticmethod
    def _event_datetime(dates: dict[str, Any], venue: dict[str, Any]) -> datetime:
        start = dates.get("start") or {}
        if start.get("dateTime"):
            return datetime.fromisoformat(str(start["dateTime"]).replace("Z", "+00:00"))
        local_date = str(start["localDate"])
        local_time = str(start.get("localTime") or "19:30:00")
        timezone = str(dates.get("timezone") or venue.get("timezone") or "UTC")
        return datetime.fromisoformat(f"{local_date}T{local_time}").replace(
            tzinfo=ZoneInfo(timezone)
        )

    def _store_cache(self, event: PublicEvent) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_bytes(
            orjson.dumps(event.model_dump(mode="json"), option=orjson.OPT_INDENT_2)
        )

    def _read_cache(self) -> PublicEvent | None:
        if not self.cache_path.exists():
            return None
        try:
            cached = PublicEvent.model_validate_json(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return cached.model_copy(update={"source": "ticketmaster_cache", "live": False})


class RanDemoService:
    """Deterministic RAN twin plus evidence-driven ChangeGuard execution."""

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        fallback_event_path: Path | None = None,
        output_root: Path | None = None,
    ) -> None:
        resolved_config = config_path or Path(
            _read_env("RAN_DEMO_CONFIG_PATH") or DEFAULT_CONFIG_PATH
        )
        self.config_path = resolved_config
        self.config_data = RanDemoConfig.model_validate_json(
            resolved_config.read_text(encoding="utf-8")
        )
        self.output_root = output_root or Path(
            _read_env("RAN_DEMO_OUTPUT_ROOT") or DEFAULT_OUTPUT_ROOT
        )
        fallback = fallback_event_path or Path(
            _read_env("RAN_DEMO_EVENT_CACHE_PATH") or DEFAULT_EVENT_PATH
        )
        self.event_adapter = TicketmasterEventAdapter(
            self.config_data,
            fallback_path=fallback,
            cache_path=self.output_root / "event-cache.json",
        )

    def config(self) -> dict[str, Any]:
        config = self.config_data
        return {
            "service": "ChangeGuard RAN digital twin",
            "config_version": config.version,
            "clock_ratio": config.simulation.clock_ratio,
            "ticketmaster_live_available": self.event_adapter.live_available,
            "event_mode": _read_env("RAN_DEMO_EVENT_MODE") or "auto",
            "scenarios": [scenario.model_dump(mode="json") for scenario in config.scenarios],
            "cells": [
                {"cell_id": cell.cell_id, "label": cell.label, "site_id": cell.site_id}
                for cell in config.cells
            ],
            "safety_boundary": "No radio, cellular network, or production controller access",
        }

    async def run(self, request: DemoRunRequest) -> dict[str, Any]:
        scenario = next(
            (item for item in self.config_data.scenarios if item.id == request.scenario),
            None,
        )
        if scenario is None:
            raise ValueError(f"Unknown demo scenario: {request.scenario}")
        run_id = f"ran-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        run_directory = self.output_root / run_id
        ledger = RunLedger(run_directory / "run.jsonl")
        event = await self.event_adapter.get_event()
        result = self._execute(run_id, event, scenario)
        for record in result["audit"]:
            await ledger.emit(
                record["event"],
                run_id=run_id,
                actor=record["actor"],
                status=record["status"],
                detail=record["detail"],
            )
        run_directory.mkdir(parents=True, exist_ok=True)
        (run_directory / "summary.json").write_bytes(
            orjson.dumps(result, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        )
        return result

    def _execute(
        self,
        run_id: str,
        event: PublicEvent,
        scenario: ScenarioConfig,
    ) -> dict[str, Any]:
        config = self.config_data
        now = datetime.now(UTC)
        stale_age = int(float(scenario.faults.get("telemetry_age_seconds", 0)))
        history = [
            self._snapshot(
                event,
                minute,
                observed_at=now - timedelta(seconds=stale_age + index * 4),
            )
            for index, minute in enumerate(reversed(config.simulation.snapshot_minutes))
        ]
        history.reverse()
        before = history[-1]
        source_cell = max(config.cells, key=lambda cell: cell.event_share)
        donors = [cell for cell in config.cells if cell.cell_id != source_cell.cell_id]
        findings = self._agent_findings(event, history, source_cell, donors)
        proposal = self._proposal(event, before, source_cell, donors, findings)
        guard = self._guard(history, proposal, source_cell, donors, now)
        audit = [
            self._audit(
                "event.detected", "Event Intelligence", "complete", self._event_detail(event)
            ),
            self._audit(
                "twin.simulated",
                "RAN Digital Twin",
                "complete",
                f"{len(history)} computed telemetry windows at "
                f"{config.simulation.clock_ratio}× time",
            ),
            self._audit(
                "remediation.proposed",
                "RAN Guardian",
                "complete",
                f"{proposal['action']['type']} · "
                f"{proposal['action']['offload_percentage']}% canary candidate",
            ),
            self._audit(
                "changeguard.evaluated",
                "ChangeGuard",
                guard["verdict"].casefold(),
                guard["summary"],
            ),
        ]
        states = [{"key": "before", "label": "Peak load", "cells": before["cells"]}]
        execution = {
            "mode": f"{config.policy.canary_pct}% canary",
            "mutations": 0,
            "duplicate_suppressed": False,
            "rollback_applied": False,
            "rollback_verified": False,
        }
        status = "BLOCKED"
        final_state = before

        if guard["verdict"] == "PASS":
            canary = self._apply_offload(
                event,
                before,
                source_cell,
                donors,
                config.policy.canary_pct,
                scenario,
                inject_donor_fault=False,
            )
            states.append({"key": "canary", "label": "5% canary", "cells": canary["cells"]})
            execution["mutations"] = 1
            canary_ok, canary_reason = self._verify(canary, before, source_cell, donors)
            audit.append(
                self._audit(
                    "controller.canary_applied",
                    "Controller Simulator",
                    "complete",
                    f"Bounded {config.policy.canary_pct}% offload applied once",
                )
            )
            audit.append(
                self._audit(
                    "canary.verified",
                    "ChangeGuard",
                    "pass" if canary_ok else "rollback",
                    canary_reason,
                )
            )
            if canary_ok:
                final_candidate = self._apply_offload(
                    event,
                    before,
                    source_cell,
                    donors,
                    int(proposal["action"]["offload_percentage"]),
                    scenario,
                    inject_donor_fault=True,
                )
                execution["mutations"] = 2
                verified, verification_reason = self._verify(
                    final_candidate, before, source_cell, donors
                )
                if verified:
                    status = "VERIFIED"
                    final_state = final_candidate
                    states.append(
                        {"key": "final", "label": "Verified state", "cells": final_state["cells"]}
                    )
                    audit.append(
                        self._audit(
                            "change.verified",
                            "ChangeGuard",
                            "verified",
                            verification_reason,
                        )
                    )
                    if bool(scenario.faults.get("duplicate_delivery", False)):
                        execution["duplicate_suppressed"] = True
                        status = "ALREADY_APPLIED"
                        audit.append(
                            self._audit(
                                "duplicate.suppressed",
                                "Idempotency Store",
                                "safe_noop",
                                "Matching operation fingerprint returned prior result; "
                                "zero extra writes",
                            )
                        )
                else:
                    status = "ROLLED_BACK"
                    execution["rollback_applied"] = True
                    execution["rollback_verified"] = True
                    final_state = before
                    states.append(
                        {
                            "key": "failed",
                            "label": "Rollback trigger",
                            "cells": final_candidate["cells"],
                        }
                    )
                    states.append(
                        {"key": "final", "label": "Baseline restored", "cells": before["cells"]}
                    )
                    audit.append(
                        self._audit(
                            "rollback.requested",
                            "ChangeGuard",
                            "rollback",
                            verification_reason,
                        )
                    )
                    audit.append(
                        self._audit(
                            "rollback.verified",
                            "Independent Verifier",
                            "verified",
                            "Configuration version and pre-change telemetry state restored",
                        )
                    )
            else:
                status = "ROLLED_BACK"
                execution["rollback_applied"] = True
                execution["rollback_verified"] = True
                final_state = before
                states.append(
                    {"key": "final", "label": "Baseline restored", "cells": before["cells"]}
                )
                audit.append(
                    self._audit(
                        "rollback.verified",
                        "Independent Verifier",
                        "verified",
                        canary_reason,
                    )
                )
        else:
            failed = [check["label"] for check in guard["checks"] if not check["passed"]]
            audit.append(
                self._audit(
                    "controller.write_withheld",
                    "ChangeGuard",
                    "blocked",
                    f"Zero writes. Failed evidence: {', '.join(failed)}",
                )
            )

        source_before = before["cells"][source_cell.cell_id]
        source_after = final_state["cells"][source_cell.cell_id]
        return {
            "run_id": run_id,
            "scenario": {
                "id": scenario.id,
                "label": scenario.label,
                "description": scenario.description,
            },
            "status": status,
            "event": event.model_dump(mode="json"),
            "source_mode": "live public feed" if event.live else "cached safe fallback",
            "simulation": {
                "clock_ratio": config.simulation.clock_ratio,
                "seed": config.simulation.seed,
                "computed_snapshots": len(history),
                "production_network_access": False,
            },
            "agent_findings": findings,
            "proposal": proposal,
            "guard": guard,
            "execution": execution,
            "network_states": states,
            "impact": {
                "stadium_prb_before_pct": source_before["dl_prb_utilization_pct"],
                "stadium_prb_after_pct": source_after["dl_prb_utilization_pct"],
                "throughput_before_mbps": source_before["median_downlink_mbps"],
                "throughput_after_mbps": source_after["median_downlink_mbps"],
            },
            "audit": audit,
            "audit_log": f"outputs/ran-demo/{run_id}/run.jsonl",
        }

    def _snapshot(
        self,
        event: PublicEvent,
        relative_minute: int,
        *,
        observed_at: datetime,
        user_overrides: dict[str, int] | None = None,
        handover_penalties: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        simulation = self.config_data.simulation
        arrival = self._interpolate_arrival(relative_minute)
        connected_event_users = (
            event.estimated_attendance * arrival * simulation.connected_user_ratio
        )
        spike = self._traffic_multiplier(relative_minute)
        cells: dict[str, dict[str, Any]] = {}
        for cell in self.config_data.cells:
            active_users = (
                user_overrides[cell.cell_id]
                if user_overrides is not None
                else round(cell.baseline_users + connected_event_users * cell.event_share)
            )
            variation_seed = f"{simulation.seed}:{cell.cell_id}:{relative_minute}:{active_users}"
            # Seeded non-cryptographic jitter makes every scenario repeatable.
            variation = random.Random(variation_seed).uniform(0.985, 1.015)  # noqa: S311
            offered_load = active_users * simulation.average_user_demand_mbps * spike * variation
            utilization = min(100.0, 100 * offered_load / cell.radio_capacity_mbps)
            pressure = max(0.0, utilization - simulation.congestion_soft_start_pct)
            per_user = cell.radio_capacity_mbps / max(active_users, 1)
            throughput_factor = max(0.55, 1.35 - pressure / 55)
            throughput = min(simulation.device_limit_mbps, per_user * throughput_factor)
            latency = simulation.base_latency_ms + (pressure**1.38) * 0.72
            handover = max(
                0.0,
                cell.base_handover_success_pct
                - max(0.0, utilization - 90) * 0.08
                - (handover_penalties or {}).get(cell.cell_id, 0),
            )
            drops = min(
                100.0,
                cell.base_drop_rate_pct + max(0.0, utilization - 84) * 0.035,
            )
            cells[cell.cell_id] = {
                "cell_id": cell.cell_id,
                "label": cell.label,
                "active_users": active_users,
                "dl_prb_utilization_pct": round(utilization, 1),
                "median_downlink_mbps": round(throughput, 1),
                "latency_p95_ms": round(latency, 1),
                "handover_success_pct": round(handover, 2),
                "session_drop_rate_pct": round(drops, 2),
                "backhaul_utilization_pct": round(
                    min(100.0, 100 * offered_load / cell.backhaul_capacity_mbps), 1
                ),
                "critical_alarms": [],
                "config_version": cell.config_version,
                "latitude": round(event.venue.latitude + cell.latitude_offset, 6),
                "longitude": round(event.venue.longitude + cell.longitude_offset, 6),
            }
        simulated_at = event.starts_at + timedelta(minutes=relative_minute)
        return {
            "relative_minute": relative_minute,
            "simulated_at": simulated_at.isoformat(),
            "observed_at": observed_at.isoformat(),
            "arrival_fraction": round(arrival, 3),
            "cells": cells,
        }

    def _apply_offload(
        self,
        event: PublicEvent,
        before: dict[str, Any],
        source: CellConfig,
        donors: list[CellConfig],
        percentage: int,
        scenario: ScenarioConfig,
        *,
        inject_donor_fault: bool,
    ) -> dict[str, Any]:
        current_users = {
            cell.cell_id: int(before["cells"][cell.cell_id]["active_users"])
            for cell in self.config_data.cells
        }
        offloaded = round(current_users[source.cell_id] * percentage / 100)
        current_users[source.cell_id] -= offloaded
        headroom = {
            donor.cell_id: max(
                1.0,
                self.config_data.policy.donor_prb_limit_pct
                - float(before["cells"][donor.cell_id]["dl_prb_utilization_pct"]),
            )
            for donor in donors
        }
        total_headroom = sum(headroom.values())
        allocated = 0
        for index, donor in enumerate(donors):
            share = (
                offloaded - allocated
                if index == len(donors) - 1
                else round(offloaded * headroom[donor.cell_id] / total_headroom)
            )
            current_users[donor.cell_id] += share
            allocated += share
        handover_penalties: dict[str, float] = {}
        if inject_donor_fault:
            extra_users = int(float(scenario.faults.get("donor_extra_users", 0)))
            if extra_users and donors:
                current_users[donors[-1].cell_id] += extra_users
            if donors:
                handover_penalties[donors[-1].cell_id] = float(
                    scenario.faults.get("handover_penalty_pct", 0)
                )
        return self._snapshot(
            event,
            int(before["relative_minute"]),
            observed_at=datetime.now(UTC),
            user_overrides=current_users,
            handover_penalties=handover_penalties,
        )

    def _agent_findings(
        self,
        event: PublicEvent,
        history: list[dict[str, Any]],
        source: CellConfig,
        donors: list[CellConfig],
    ) -> list[dict[str, Any]]:
        policy = self.config_data.policy
        window = history[-policy.sustained_window_points :]
        source_values = [
            float(item["cells"][source.cell_id]["dl_prb_utilization_pct"]) for item in window
        ]
        latest = history[-1]
        donor_values = {
            donor.cell_id: latest["cells"][donor.cell_id]["dl_prb_utilization_pct"]
            for donor in donors
        }
        return [
            {
                "agent": "Event Context Agent",
                "finding": (
                    f"{event.estimated_attendance:,} estimated attendees near {event.venue.name}"
                ),
                "evidence": [f"event:{event.event_id}"],
            },
            {
                "agent": "Capacity Agent",
                "finding": (
                    f"{source.cell_id} sustained {min(source_values):.1f}%–"
                    f"{max(source_values):.1f}% PRB"
                ),
                "evidence": [
                    f"telemetry:{source.cell_id}:{item['relative_minute']}" for item in window
                ],
            },
            {
                "agent": "Topology Agent",
                "finding": "Donor headroom: "
                + ", ".join(f"{cell_id} {value:.1f}%" for cell_id, value in donor_values.items()),
                "evidence": [
                    f"topology:{source.cell_id}",
                    *[f"telemetry:{item}" for item in donor_values],
                ],
            },
            {
                "agent": "Remediation Agent",
                "finding": "Typed mobility load balancing is available within configured bounds",
                "evidence": [f"config:{source.config_version}", "policy:ran-demo-v1"],
            },
        ]

    def _proposal(
        self,
        event: PublicEvent,
        latest: dict[str, Any],
        source: CellConfig,
        donors: list[CellConfig],
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        policy = self.config_data.policy
        utilization = float(latest["cells"][source.cell_id]["dl_prb_utilization_pct"])
        calculated = round(
            max(0.0, utilization - policy.target_prb_pct) / max(utilization, 1) * 100
        )
        offload = min(
            policy.maximum_offload_pct,
            max(policy.minimum_offload_pct, calculated),
        )
        action = {
            "type": "MOBILITY_LOAD_BALANCING",
            "source": source.cell_id,
            "targets": [donor.cell_id for donor in donors],
            "offload_percentage": offload,
            "parameter_delta_db": round(0.15 * offload, 2),
            "expected_config_version": source.config_version,
        }
        fingerprint_input = {
            "event_id": event.event_id,
            "action": action,
            "evidence": [item for finding in findings for item in finding["evidence"]],
        }
        fingerprint = hashlib.sha256(
            orjson.dumps(fingerprint_input, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        return {
            "proposal_id": f"PROP-{fingerprint[:10].upper()}",
            "fingerprint": fingerprint,
            "action": action,
            "reason": f"{source.cell_id} sustained congestion during event ingress",
            "evidence_refs": fingerprint_input["evidence"],
        }

    def _guard(
        self,
        history: list[dict[str, Any]],
        proposal: dict[str, Any],
        source: CellConfig,
        donors: list[CellConfig],
        now: datetime,
    ) -> dict[str, Any]:
        policy = self.config_data.policy
        latest = history[-1]
        observed = datetime.fromisoformat(str(latest["observed_at"]))
        age_seconds = max(0.0, (now - observed).total_seconds())
        window = history[-policy.sustained_window_points :]
        action = proposal["action"]
        checks = [
            self._check(
                "Telemetry freshness",
                age_seconds <= policy.telemetry_max_age_seconds,
                f"{age_seconds:.0f}s old · limit {policy.telemetry_max_age_seconds}s",
                "TELEMETRY_STALE",
            ),
            self._check(
                "Sustained congestion",
                len(window) == policy.sustained_window_points
                and all(
                    float(item["cells"][source.cell_id]["dl_prb_utilization_pct"])
                    >= policy.congestion_threshold_pct
                    for item in window
                ),
                f"{policy.sustained_window_points} authoritative windows required",
                "CONGESTION_NOT_SUSTAINED",
            ),
            self._check(
                "Donor headroom",
                all(
                    float(latest["cells"][donor.cell_id]["dl_prb_utilization_pct"])
                    < policy.donor_prb_limit_pct
                    for donor in donors
                ),
                f"All donors below {policy.donor_prb_limit_pct:.0f}%",
                "INSUFFICIENT_DONOR_HEADROOM",
            ),
            self._check(
                "Critical alarms",
                not any(
                    latest["cells"][cell.cell_id]["critical_alarms"]
                    for cell in self.config_data.cells
                ),
                "No active critical alarm",
                "CRITICAL_ALARM_ACTIVE",
            ),
            self._check(
                "Configuration version",
                int(action["expected_config_version"])
                == int(latest["cells"][source.cell_id]["config_version"]),
                f"Expected {action['expected_config_version']}",
                "CONFIG_VERSION_MISMATCH",
            ),
            self._check(
                "Change window",
                policy.change_window_open,
                "Configured demo change window",
                "CHANGE_WINDOW_CLOSED",
            ),
            self._check(
                "Rollback snapshot",
                bool(latest["cells"]),
                "Pre-change state captured",
                "ROLLBACK_UNAVAILABLE",
            ),
            self._check(
                "Parameter bounds",
                policy.minimum_offload_pct
                <= int(action["offload_percentage"])
                <= policy.maximum_offload_pct,
                f"Allowed {policy.minimum_offload_pct}%–{policy.maximum_offload_pct}%",
                "PARAMETER_OUT_OF_BOUNDS",
            ),
        ]
        failed = [check for check in checks if not check["passed"]]
        verdict = "BLOCK" if failed else "PASS"
        summary = (
            f"Blocked: {failed[0]['code']}"
            if failed
            else f"All {len(checks)} checks passed · {policy.canary_pct}% canary authorized"
        )
        return {
            "verdict": verdict,
            "execution_mode": f"{policy.canary_pct}% CANARY",
            "summary": summary,
            "checks": checks,
        }

    def _verify(
        self,
        snapshot: dict[str, Any],
        before: dict[str, Any],
        source: CellConfig,
        donors: list[CellConfig],
    ) -> tuple[bool, str]:
        policy = self.config_data.policy
        cells = snapshot["cells"]
        failures: list[str] = []
        for donor in donors:
            metric = cells[donor.cell_id]
            if float(metric["dl_prb_utilization_pct"]) >= policy.donor_prb_limit_pct:
                failures.append(f"{donor.cell_id} donor PRB {metric['dl_prb_utilization_pct']}%")
        for cell in self.config_data.cells:
            metric = cells[cell.cell_id]
            if float(metric["handover_success_pct"]) < policy.minimum_handover_success_pct:
                failures.append(f"{cell.cell_id} handover {metric['handover_success_pct']}%")
            if float(metric["session_drop_rate_pct"]) > policy.maximum_session_drop_rate_pct:
                failures.append(f"{cell.cell_id} drops {metric['session_drop_rate_pct']}%")
            if float(metric["latency_p95_ms"]) > policy.maximum_latency_p95_ms:
                failures.append(f"{cell.cell_id} latency {metric['latency_p95_ms']}ms")
        source_before = float(before["cells"][source.cell_id]["dl_prb_utilization_pct"])
        source_after = float(cells[source.cell_id]["dl_prb_utilization_pct"])
        if source_after >= source_before:
            failures.append(f"{source.cell_id} congestion did not improve")
        if failures:
            return False, "Rollback condition: " + "; ".join(failures)
        return (
            True,
            f"{source.cell_id} PRB improved {source_before:.1f}% → "
            f"{source_after:.1f}% with donor safety intact",
        )

    def _interpolate_arrival(self, minute: int) -> float:
        points = self.config_data.simulation.arrival_curve
        if minute <= points[0].relative_minute:
            return points[0].fraction
        if minute >= points[-1].relative_minute:
            return points[-1].fraction
        for left, right in zip(points, points[1:], strict=False):
            if left.relative_minute <= minute <= right.relative_minute:
                span = right.relative_minute - left.relative_minute
                progress = (minute - left.relative_minute) / span
                return left.fraction + (right.fraction - left.fraction) * progress
        raise RuntimeError("Arrival curve interpolation failed")

    def _traffic_multiplier(self, minute: int) -> float:
        multiplier = 1.0
        for spike in self.config_data.simulation.traffic_spikes:
            distance = abs(minute - spike.relative_minute)
            if distance <= spike.width_minutes:
                weight = 1 - distance / spike.width_minutes
                multiplier = max(multiplier, 1 + (spike.multiplier - 1) * weight)
        return multiplier

    @staticmethod
    def _check(label: str, passed: bool, detail: str, code: str) -> dict[str, Any]:
        return {"label": label, "passed": passed, "detail": detail, "code": code}

    @staticmethod
    def _audit(event: str, actor: str, status: str, detail: str) -> dict[str, str]:
        return {"event": event, "actor": actor, "status": status, "detail": detail}

    @staticmethod
    def _event_detail(event: PublicEvent) -> str:
        source = "live Ticketmaster" if event.live else event.source.replace("_", " ")
        return f"{event.name} · {event.estimated_attendance:,} estimated · {source}"
