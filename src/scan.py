import argparse
import asyncio


HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"


def parse_args():
    parser = argparse.ArgumentParser(description="Scan for nearby BLE devices.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="seconds to scan before printing results",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="case-insensitive substring to match against advertised device names",
    )
    parser.add_argument(
        "--heart-rate-only",
        action="store_true",
        help="only show devices advertising the Bluetooth heart-rate service",
    )
    return parser.parse_args()


def matches_name(name, query):
    if query is None:
        return True
    if not name:
        return False
    return query.casefold() in name.casefold()


def is_heart_rate_device(advertisement):
    service_uuids = {uuid.casefold() for uuid in advertisement.service_uuids}
    return HEART_RATE_SERVICE_UUID in service_uuids


def format_device(device, advertisement):
    name = device.name or advertisement.local_name or "(unnamed)"
    rssi = advertisement.rssi
    services = ", ".join(advertisement.service_uuids) or "none advertised"
    marker = " heart-rate" if is_heart_rate_device(advertisement) else ""

    return (
        f"{name}{marker}\n"
        f"  address: {device.address}\n"
        f"  rssi: {rssi} dBm\n"
        f"  services: {services}"
    )


async def scan(timeout, name_filter, heart_rate_only):
    try:
        from bleak import BleakScanner
    except ModuleNotFoundError as exc:
        if exc.name == "bleak":
            raise RuntimeError("bleak is not installed. Try: python3 -m pip install -r requirements.txt") from exc
        raise

    print(f"Scanning for {timeout:g} seconds...")
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)

    matches = []
    for device, advertisement in discovered.values():
        display_name = device.name or advertisement.local_name
        if not matches_name(display_name, name_filter):
            continue
        if heart_rate_only and not is_heart_rate_device(advertisement):
            continue
        matches.append((device, advertisement))

    matches.sort(key=lambda item: item[1].rssi, reverse=True)
    return matches


def main():
    args = parse_args()
    try:
        matches = asyncio.run(scan(args.timeout, args.name, args.heart_rate_only))
    except RuntimeError as exc:
        print(exc)
        return 1

    if not matches:
        print("No matching BLE devices found.")
        return 1

    print(f"Found {len(matches)} matching BLE device(s):")
    for device, advertisement in matches:
        print()
        print(format_device(device, advertisement))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
