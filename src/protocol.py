from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ProtocolPhase:
    name: str
    duration_s: int
    instructions: str
    measurement_point: str | None = None


@dataclass(frozen=True)
class StepTestProtocol:
    protocol_id: str
    version: int
    name: str
    cadence_spm: int
    step_height_in: int
    phases: tuple[ProtocolPhase, ...]

    @property
    def total_duration_s(self) -> int:
        return sum(phase.duration_s for phase in self.phases)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["phases"] = [asdict(phase) for phase in self.phases]
        return data


YMCA_STEP_TEST_V1 = StepTestProtocol(
    protocol_id="ymca_step_test",
    version=1,
    name="YMCA 3-Minute Step Test",
    cadence_spm=96,
    step_height_in=12,
    phases=(
        ProtocolPhase(
            name="setup",
            duration_s=15,
            instructions="Prepare sensor contact and confirm cadence.",
        ),
        ProtocolPhase(
            name="stepping",
            duration_s=180,
            instructions="Step at 96 beats per minute on a 12 inch step.",
            measurement_point="active_work",
        ),
        ProtocolPhase(
            name="immediate_recovery",
            duration_s=15,
            instructions="Sit immediately after stepping stops.",
            measurement_point="post_step_transition",
        ),
        ProtocolPhase(
            name="one_minute_recovery",
            duration_s=60,
            instructions="Remain seated while recovery heartbeats are recorded.",
            measurement_point="one_minute_recovery",
        ),
    ),
)
