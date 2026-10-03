from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from typing import Iterable

import serial
from serial.tools import list_ports


ESP_USB_VENDORS = {
    0x10C4: "Silicon Labs (CP210x)",
    0x1A86: "QinHeng (CH34x)",
    0x2341: "Arduino",
    0x303A: "Espressif",
    0x0403: "FTDI",
}


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str
    vid: str | None
    pid: str | None
    usb_vendor: str | None
    manufacturer: str | None
    product: str | None
    serial_number: str | None
    location: str | None


@dataclass
class Capture:
    baudrate: int
    bytes_received: int
    text: str
    hex_preview: str
    indicators: list[str] = field(default_factory=list)
    error: str | None = None


def _hex(value: int | None) -> str | None:
    return f"0x{value:04x}" if value is not None else None


def discover_ports() -> list[PortInfo]:
    ports: list[PortInfo] = []
    for item in list_ports.comports():
        ports.append(
            PortInfo(
                device=item.device,
                description=item.description,
                hwid=item.hwid,
                vid=_hex(item.vid),
                pid=_hex(item.pid),
                usb_vendor=ESP_USB_VENDORS.get(item.vid),
                manufacturer=item.manufacturer,
                product=item.product,
                serial_number=item.serial_number,
                location=item.location,
            )
        )
    return ports


def infer_indicators(text: str) -> list[str]:
    needles = {
        "ESP boot ROM banner": ("rst:", "boot:", "ets "),
        "ESP-IDF application": ("ESP-IDF", "I (", "Guru Meditation"),
        "Arduino application": ("Arduino",),
        "AT firmware": ("ready", "+GMR", "WIFI "),
        "Serial console or shell": ("login:", "# ", "$ "),
    }
    lower = text.lower()
    return [label for label, terms in needles.items() if any(term.lower() in lower for term in terms)]


def passive_capture(port: str, baudrate: int, seconds: float, max_bytes: int) -> Capture:
    """Listen only. Deliberately does not toggle DTR/RTS or transmit data."""
    received = bytearray()
    try:
        with serial.Serial(port=port, baudrate=baudrate, timeout=0.1, write_timeout=0.1) as connection:
            # Avoid driving auto-program reset circuitry while opening the port.
            connection.dtr = False
            connection.rts = False
            deadline = monotonic() + seconds
            while monotonic() < deadline and len(received) < max_bytes:
                waiting = connection.in_waiting
                received.extend(connection.read(min(max(waiting, 1), max_bytes - len(received))))
                sleep(0.01)
    except (serial.SerialException, OSError) as exc:
        return Capture(baudrate, 0, "", "", error=str(exc))

    text = received.decode("utf-8", errors="replace")
    return Capture(
        baudrate=baudrate,
        bytes_received=len(received),
        text=text,
        hex_preview=received[:256].hex(" "),
        indicators=infer_indicators(text),
    )


def safe_at_probe(port: str, baudrate: int) -> str:
    """Optional non-persistent AT probe. Requires explicit user opt-in."""
    try:
        with serial.Serial(port=port, baudrate=baudrate, timeout=0.5, write_timeout=0.5) as connection:
            connection.dtr = False
            connection.rts = False
            connection.reset_input_buffer()
            connection.write(b"AT\r\n")
            connection.flush()
            return connection.read(512).decode("utf-8", errors="replace")
    except (serial.SerialException, OSError) as exc:
        return f"ERROR: {exc}"


def selected_ports(all_ports: Iterable[PortInfo], requested: list[str] | None) -> list[PortInfo]:
    if not requested:
        return list(all_ports)
    known = {item.device: item for item in all_ports}
    return [known.get(name, PortInfo(name, "not currently enumerated", "", None, None, None, None, None, None, None)) for name in requested]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only ESP USB serial discovery")
    parser.add_argument("--list", action="store_true", help="list serial ports and exit")
    parser.add_argument("--port", action="append", help="port to listen on; repeatable")
    parser.add_argument("--baud", action="append", type=int, default=[], help="baud rate to listen at; repeatable")
    parser.add_argument("--seconds", type=float, default=2.0, help="listen time per baud rate")
    parser.add_argument("--max-bytes", type=int, default=4096, help="maximum capture size per baud rate")
    parser.add_argument("--at-probe", action="store_true", help="send AT\\r\\n once; disabled by default")
    parser.add_argument("--json-out", type=Path, help="write the report to this JSON path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.seconds <= 0 or args.max_bytes <= 0:
        raise SystemExit("--seconds and --max-bytes must be positive")

    inventory = discover_ports()
    if args.list:
        print(json.dumps([asdict(port) for port in inventory], indent=2))
        return

    ports = selected_ports(inventory, args.port)
    if not ports:
        raise SystemExit("No serial ports found. Connect a device or specify --port.")
    bauds = args.baud or [115200, 74880, 921600]
    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "passive capture" + (" plus explicit AT probe" if args.at_probe else ""),
        "safety": "No flash write, erase, reset pulse, bootloader entry, or persistent configuration change is performed.",
        "ports": [],
    }
    report_ports = []
    for port in ports:
        captures = [asdict(passive_capture(port.device, baud, args.seconds, args.max_bytes)) for baud in bauds]
        entry: dict[str, object] = {"port": asdict(port), "captures": captures}
        if args.at_probe:
            entry["at_probe_response"] = safe_at_probe(port.device, bauds[0])
        report_ports.append(entry)
    report["ports"] = report_ports
    output = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.write_text(output + "\n", encoding="utf-8")
        print(f"Wrote {args.json_out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
