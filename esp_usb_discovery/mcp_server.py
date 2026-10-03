"""Read-only MCP adapter for an ESP Probe JSONL serial device.

This deliberately implements the small MCP stdio surface we need instead of
adding a second runtime dependency. The ESP firmware remains a simple,
profile-aware JSONL device; an MCP client talks to this process.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import monotonic
from typing import Any

import serial


PROTOCOL_VERSION = "2024-11-05"
ROOT_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT_DIR / "profiles"


TOOLS: list[dict[str, Any]] = [
    {
        "name": "device.get_inventory",
        "description": "Read the ESP chip, flash, runtime, identity, Wi-Fi, and board inventory.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "device.get_capabilities",
        "description": "Read the diagnostic capabilities advertised by the firmware.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "device.get_boot_capture",
        "description": "Read currently buffered boot/application serial output without resetting the device.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "cyd.get_display_status",
        "description": "Read the CYD display initialization and controller-readback status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "cyd.read_flash_id",
        "description": "Read the flash JEDEC ID and runtime flash geometry.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "device.get_gpio_map",
        "description": "Read the selected board profile's documented and reserved GPIO map.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


class ProbeSerial:
    def __init__(self, port: str, baud: int, timeout: float) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.connection: serial.Serial | None = None

    def open(self) -> None:
        if self.connection is not None:
            return
        self.connection = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=0.1,
            write_timeout=0.5,
        )
        # Do not intentionally pulse USB-UART auto-reset lines.
        self.connection.dtr = False
        self.connection.rts = False

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _read_lines(self, seconds: float) -> list[str]:
        assert self.connection is not None
        lines: list[str] = []
        buffer = bytearray()
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            chunk = self.connection.read(max(self.connection.in_waiting, 1))
            if not chunk:
                continue
            buffer.extend(chunk)
            while b"\n" in buffer:
                raw, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                lines.append(raw.decode("utf-8", errors="replace").strip())
        if buffer:
            lines.append(buffer.decode("utf-8", errors="replace").strip())
        return [line for line in lines if line]

    def command(self, command: str, expected_type: str, timeout: float | None = None) -> dict[str, Any]:
        self.open()
        assert self.connection is not None
        self.connection.reset_input_buffer()
        self.connection.write((command + "\n").encode("ascii"))
        self.connection.flush()
        raw_lines = self._read_lines(timeout or self.timeout)
        for line in raw_lines:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("type") == expected_type:
                return message
            if message.get("type") == "error":
                raise RuntimeError(message.get("error", "device error"))
        raise TimeoutError(f"timed out waiting for {expected_type} from {self.port}")

    def capture(self, seconds: float = 0.5) -> str:
        self.open()
        return "\n".join(self._read_lines(seconds))


class ProbeMcpServer:
    def __init__(self, probe: ProbeSerial, profile: str) -> None:
        self.probe = probe
        self.profile = profile

    def _result(self, value: Any, is_error: bool = False) -> dict[str, Any]:
        text = json.dumps(value, separators=(",", ":")) if not isinstance(value, str) else value
        result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
        if isinstance(value, (dict, list)):
            result["structuredContent"] = value
        if is_error:
            result["isError"] = True
        return result

    def call_tool(self, name: str) -> dict[str, Any]:
        if name == "device.get_inventory":
            return self._result(self.probe.command("inventory", "inventory"))
        if name == "device.get_capabilities":
            return self._result(self.probe.command("hello", "esp-probe"))
        if name == "device.get_boot_capture":
            return self._result(self.probe.capture())
        if name in {"cyd.get_display_status", "cyd.read_flash_id"}:
            inventory = self.probe.command("inventory", "inventory")
            key = "cyd_display" if name.endswith("display_status") else "flash"
            return self._result(inventory.get(key, {}))
        if name == "device.get_gpio_map":
            profile_path = PROFILE_DIR / f"{self.profile}.json"
            if not profile_path.is_file():
                raise FileNotFoundError(f"profile not found: {self.profile}")
            return self._result(json.loads(profile_path.read_text(encoding="utf-8")))
        raise KeyError(f"unknown tool: {name}")

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        if request_id is None and method and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "esp-probe", "version": "0.1.0"},
                },
            }
        if method == "ping":
            result: dict[str, Any] = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            result = self.call_tool(params["name"])
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def serve(self) -> None:
        for raw in sys.stdin:
            if not raw.strip():
                continue
            request: Any = None
            try:
                request = json.loads(raw)
                response = self.handle(request)
                if response is not None:
                    print(json.dumps(response, separators=(",", ":")), flush=True)
            except Exception as exc:  # Keep the stdio server alive after tool errors.
                request_id = request.get("id") if isinstance(request, dict) else None
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32000, "message": str(exc)},
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only MCP adapter for ESP Probe")
    parser.add_argument("--port", required=True, help="USB serial port connected to the probe")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--profile", default="cyd-esp32-2432s024")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = ProbeMcpServer(ProbeSerial(args.port, args.baud, args.timeout), args.profile)
    try:
        server.serve()
    finally:
        server.probe.close()


if __name__ == "__main__":
    main()
