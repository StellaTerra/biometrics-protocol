from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from protocol import StepTestProtocol


DEFAULT_SESSION_DIR = Path(os.environ.get("BIOMETRICS_SESSION_DIR", "sessions"))
SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    path: Path
    started_at_wall: str
    protocol_name: str
    completed: bool
    heartbeat_count: int
    average_recovery_bpm: float | None


class SessionRecorder:
    def __init__(
        self,
        protocol: StepTestProtocol,
        directory: Path | str = DEFAULT_SESSION_DIR,
    ):
        self.protocol = protocol
        self.directory = Path(directory)
        self.session_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        self.started_at_wall = utc_now_iso()
        self._started_monotonic = monotonic()
        self._events: list[dict[str, Any]] = []
        self.path = self.directory / f"{self.session_id}.json"
        self._finalized = False

        self.directory.mkdir(parents=True, exist_ok=True)
        self.record_event(
            "session_started",
            protocol_id=protocol.protocol_id,
            protocol_version=protocol.version,
        )

    @property
    def elapsed_s(self) -> float:
        return monotonic() - self._started_monotonic

    def record_event(self, event_type: str, **data: Any) -> dict[str, Any]:
        if self._finalized:
            raise RuntimeError("cannot record events after session finalization")

        event = {
            "type": event_type,
            "t_monotonic_s": round(self.elapsed_s, 6),
            "wall_time": utc_now_iso(),
            **data,
        }
        self._events.append(event)
        self._write(finalized=False)
        return event

    def record_heartbeat(
        self,
        *,
        t_monotonic_s: float | None = None,
        wall_time: str | None = None,
        rr_ms: int | float | None = None,
        sensor_time_s: float | None = None,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "t_monotonic_s": round(t_monotonic_s if t_monotonic_s is not None else self.elapsed_s, 6),
            "wall_time": wall_time or utc_now_iso(),
            "source": source or {},
        }
        if rr_ms is not None:
            payload["rr_ms"] = rr_ms
        if sensor_time_s is not None:
            payload["sensor_time_s"] = sensor_time_s
        return self.record_event("heartbeat", **payload)

    def complete(self, status: str = "completed") -> Path:
        if not self._finalized:
            self.record_event("session_completed", status=status)
            self._finalized = True
            self._write(finalized=True)
        return self.path

    def _document(self, finalized: bool) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "started_at_wall": self.started_at_wall,
            "finalized": finalized,
            "protocol": self.protocol.to_dict(),
            "events": self._events,
        }

    def _write(self, finalized: bool) -> None:
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self._document(finalized=finalized), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.path)


def load_session(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def derive_bpm_from_heartbeats(events: list[dict[str, Any]], window_s: float = 15.0) -> float | None:
    heartbeats = sorted(
        event["t_monotonic_s"]
        for event in events
        if event.get("type") == "heartbeat" and isinstance(event.get("t_monotonic_s"), (int, float))
    )
    if len(heartbeats) < 2:
        return None

    end = heartbeats[-1]
    start = max(heartbeats[0], end - window_s)
    window = [timestamp for timestamp in heartbeats if timestamp >= start]
    if len(window) < 2:
        return None
    duration = window[-1] - window[0]
    if duration <= 0:
        return None
    return (len(window) - 1) * 60.0 / duration


def average_recovery_bpm(session: dict[str, Any]) -> float | None:
    phase_start: float | None = None
    phase_end: float | None = None
    expected_duration_s = 60.0
    for phase in session.get("protocol", {}).get("phases", []):
        if phase.get("name") == "one_minute_recovery":
            expected_duration_s = float(phase.get("duration_s", expected_duration_s))
            break

    for event in session.get("events", []):
        if event.get("type") == "phase_started" and event.get("phase") == "one_minute_recovery":
            phase_start = event.get("t_monotonic_s")
        if event.get("type") == "phase_completed" and event.get("phase") == "one_minute_recovery":
            phase_end = event.get("t_monotonic_s")

    if phase_start is None:
        return None
    if phase_end is None or phase_end - phase_start < expected_duration_s * 0.8:
        phase_end = phase_start + expected_duration_s

    heartbeats = [
        event
        for event in session.get("events", [])
        if event.get("type") == "heartbeat"
        and isinstance(event.get("t_monotonic_s"), (int, float))
        and phase_start <= event["t_monotonic_s"] <= phase_end
    ]
    return derive_bpm_from_heartbeats(heartbeats, window_s=max(1.0, phase_end - phase_start))


def list_sessions(directory: Path | str = DEFAULT_SESSION_DIR) -> list[SessionSummary]:
    root = Path(directory)
    if not root.exists():
        return []

    summaries: list[SessionSummary] = []
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            session = load_session(path)
        except (OSError, json.JSONDecodeError):
            continue
        events = session.get("events", [])
        summaries.append(
            SessionSummary(
                session_id=session.get("session_id", path.stem),
                path=path,
                started_at_wall=session.get("started_at_wall", ""),
                protocol_name=session.get("protocol", {}).get("name", "Unknown protocol"),
                completed=any(event.get("type") == "session_completed" for event in events),
                heartbeat_count=sum(1 for event in events if event.get("type") == "heartbeat"),
                average_recovery_bpm=average_recovery_bpm(session),
            )
        )
    return summaries
