import argparse
import asyncio

from polar import PolarH10Stream


def parse_args():
    parser = argparse.ArgumentParser(
        description="Connect to a BLE heart-rate sensor and print live heartbeat events."
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


async def stream_heart_rate(args):
    stream = PolarH10Stream(
        name=args.name,
        address=args.address,
        scan_timeout=args.scan_timeout,
    )

    def on_status(status):
        print(f"sensor_status={status}")

    def on_heartbeat(heartbeat):
        bpm = f"{heartbeat.derived_bpm:3}" if heartbeat.derived_bpm is not None else " --"
        rr = f"{heartbeat.rr_ms:4}" if heartbeat.rr_ms is not None else "  --"
        sensor_time = (
            f"{heartbeat.sensor_time_s:.3f}"
            if heartbeat.sensor_time_s is not None
            else "unknown"
        )
        print(
            f"{heartbeat.t_monotonic_s:6.1f}s  bpm={bpm}  rr={rr} ms  sensor_time={sensor_time}"
        )

    await stream.connect(on_heartbeat=on_heartbeat, on_status=on_status)
    print(f"Streaming heartbeats for {args.duration:g} seconds...")
    try:
        await asyncio.sleep(args.duration)
    finally:
        await stream.disconnect()


async def run():
    args = parse_args()
    await stream_heart_rate(args)
    return 0


def main():
    try:
        return asyncio.run(run())
    except RuntimeError as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
