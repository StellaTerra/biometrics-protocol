from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Callable, Any

from session_store import utc_now_iso


@dataclass(frozen=True)
class HeartbeatEvent:
    t_monotonic_s: float
    wall_time: str
    rr_ms: int | float | None
    sensor_time_s: float | None
    source: dict[str, str | None]
    derived_bpm: int | None = None


class PolarH10Stream:
    def __init__(
        self,
        *,
        name: str = "Polar",
        address: str | None = None,
        scan_timeout: float = 10.0,
    ):
        self.name = name
        self.address = address
        self.scan_timeout = scan_timeout
        self.device = None
        self.client: Any | None = None
        self.heartrate: Any | None = None
        self._started_monotonic: float | None = None
        self._on_heartbeat: Callable[[HeartbeatEvent], None] | None = None
        self._on_status: Callable[[str], None] | None = None
        self._stop_event: asyncio.Event | None = None

    async def find_device(self):
        from scan import HEART_RATE_SERVICE_UUID, scan

        matches = await scan(
            timeout=self.scan_timeout,
            name_filter=None if self.address else self.name,
            heart_rate_only=False,
        )

        if self.address:
            address = self.address.casefold()
            matches = [
                (device, advertisement)
                for device, advertisement in matches
                if device.address.casefold() == address
            ]

        heart_rate_matches = [
            (device, advertisement)
            for device, advertisement in matches
            if HEART_RATE_SERVICE_UUID in {uuid.casefold() for uuid in advertisement.service_uuids}
        ]
        return (heart_rate_matches or matches)[0] if matches else None

    async def connect(
        self,
        on_heartbeat: Callable[[HeartbeatEvent], None],
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._on_heartbeat = on_heartbeat
        self._on_status = on_status
        self._emit_status("scanning")
        result = await self.find_device()
        if result is None:
            self._emit_status("no_device")
            raise RuntimeError("No matching BLE heart-rate device found.")

        self.device, _advertisement = result
        self._stop_event = asyncio.Event()
        self._started_monotonic = monotonic()

        try:
            from bleak import BleakClient
            from bleakheart import HeartRate
        except ModuleNotFoundError as exc:
            package = exc.name or "BLE dependency"
            self._emit_status("dependency_missing")
            raise RuntimeError(
                f"{package} is not installed. Try: python3 -m pip install -r requirements.txt"
            ) from exc

        def disconnected_callback(_client):
            self._emit_status("disconnected")
            if self._stop_event is not None:
                self._stop_event.set()

        self._emit_status("connecting")
        self.client = BleakClient(self.device, disconnected_callback=disconnected_callback)
        await self.client.connect()
        self._emit_status("connected")

        self.heartrate = HeartRate(
            self.client,
            callback=self._heart_rate_callback,
            instant_rate=True,
            unpack=True,
        )
        await self.heartrate.start_notify()
        self._emit_status("streaming")

    async def wait_until_stopped(self) -> None:
        if self._stop_event is not None:
            await self._stop_event.wait()

    async def disconnect(self) -> None:
        if self.heartrate is not None and self.client is not None and self.client.is_connected:
            await self.heartrate.stop_notify()
        if self.client is not None and self.client.is_connected:
            await self.client.disconnect()
        self.heartrate = None
        self.client = None
        self._emit_status("disconnected")

    def _heart_rate_callback(self, frame) -> None:
        _kind, timestamp_ns, heart_rate, _energy = frame
        derived_bpm, rr_ms = self._unpack_heart_rate(heart_rate)
        sensor_time_s = timestamp_ns / 1_000_000_000 if timestamp_ns is not None else None
        started = self._started_monotonic or monotonic()
        heartbeat = HeartbeatEvent(
            t_monotonic_s=monotonic() - started,
            wall_time=utc_now_iso(),
            rr_ms=rr_ms,
            sensor_time_s=sensor_time_s,
            source={
                "name": getattr(self.device, "name", None),
                "address": getattr(self.device, "address", None),
            },
            derived_bpm=derived_bpm,
        )
        if self._on_heartbeat is not None:
            self._on_heartbeat(heartbeat)

    @staticmethod
    def _unpack_heart_rate(heart_rate) -> tuple[int | None, int | float | None]:
        if isinstance(heart_rate, tuple):
            bpm = heart_rate[0] if heart_rate else None
            rr = heart_rate[1] if len(heart_rate) > 1 else None
            if isinstance(rr, list):
                rr = rr[-1] if rr else None
            return bpm, rr
        if isinstance(heart_rate, int):
            return heart_rate, None
        return None, None

    def _emit_status(self, status: str) -> None:
        if self._on_status is not None:
            self._on_status(status)
