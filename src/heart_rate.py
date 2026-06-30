import argparse
import asyncio
from time import monotonic

from bleak import BleakClient
from bleakheart import HeartRate

from scan import HEART_RATE_SERVICE_UUID, scan


def parse_args():
    parser = argparse.ArgumentParser(
        description="Connect to a BLE heart-rate sensor and print live samples."
    )
    parser.add_argument(
        "--name",
        default="Polar",
        help="case-insensitive device-name substring to scan for",
    )
    parser.add_argument(
        "--address",
        default=None,
        help="exact BLE device address to connect to",
    )
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=10.0,
        help="seconds to scan while looking for the device",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="seconds to stream heart-rate data after connecting",
    )
    return parser.parse_args()


def heart_rate_callback(start_time):
    def callback(frame):
        _kind, timestamp_ns, heart_rate, _energy = frame
        bpm, rr_ms = heart_rate
        elapsed = monotonic() - start_time
        timestamp_s = timestamp_ns / 1_000_000_000
        print(
            f"{elapsed:6.1f}s  bpm={bpm:3}  rr={rr_ms:4} ms  sensor_time={timestamp_s:.3f}"
        )

    return callback


async def find_heart_rate_device(address, name, scan_timeout):
    matches = await scan(
        timeout=scan_timeout,
        name_filter=None if address else name,
        heart_rate_only=False,
    )

    if address:
        address = address.casefold()
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


async def stream_heart_rate(device, duration):
    print(f"Connecting to {device.name or '(unnamed)'} at {device.address}...")
    async with BleakClient(device) as client:
        print(f"Connected: {client.is_connected}")
        print(f"Streaming heart-rate data for {duration:g} seconds...")

        heartrate = HeartRate(
            client,
            callback=heart_rate_callback(monotonic()),
            instant_rate=True,
            unpack=True,
        )

        await heartrate.start_notify()
        try:
            await asyncio.sleep(duration)
        finally:
            if client.is_connected:
                await heartrate.stop_notify()


async def run():
    args = parse_args()
    result = await find_heart_rate_device(args.address, args.name, args.scan_timeout)

    if result is None:
        print("No matching BLE heart-rate device found.")
        return 1

    device, _advertisement = result
    await stream_heart_rate(device, args.duration)
    return 0


def main():
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
