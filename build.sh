#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE_DIR="$ROOT_DIR/firmware/esp_probe"
PIO_BIN="${PIO_BIN:-pio}"
PIO_ENV="${PIO_ENV:-esp32-cyd-024}"
PORT="${PORT:-}"
export PLATFORMIO_CORE_DIR="${PLATFORMIO_CORE_DIR:-$ROOT_DIR/.pio-home}"

usage() {
  cat <<EOF
Usage: ./build.sh <command>

Commands:
  build       Compile the selected firmware (default)
  flash       Compile and upload; requires PORT=/dev/...
  monitor     Open the serial monitor; requires PORT=/dev/...
  all         Build, flash, then open the monitor
  package     Build and copy firmware artifacts to artifacts/<environment>/
  clean       Remove PlatformIO build output
  list        List configured PlatformIO environments
  help        Show this help

Environment:
  PIO_ENV=esp32-cyd-024       Target environment
  PORT=/dev/cu.usbserial-2110 Serial port for flash/monitor
  MONITOR_BAUD=115200         Optional monitor speed override
  PLATFORMIO_CORE_DIR=...     PlatformIO cache/toolchain location

Examples:
  ./build.sh build
  PIO_ENV=esp32-s3-devkitc-1 ./build.sh build
  PORT=/dev/cu.usbserial-2110 ./build.sh flash
  PIO_ENV=esp32-cyd-024 PORT=/dev/cu.usbserial-2110 ./build.sh all
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 127
  }
}

require_port() {
  [[ -n "$PORT" ]] || {
    echo "Set PORT explicitly, for example PORT=/dev/cu.usbserial-2110" >&2
    exit 2
  }
}

pio_run() {
  (cd "$FIRMWARE_DIR" && "$PIO_BIN" run -e "$PIO_ENV" "$@")
}

build() {
  pio_run
}

flash() {
  require_port
  pio_run
  pio_run --upload-port "$PORT" -t upload
}

monitor() {
  require_port
  monitor_args=(--monitor-port "$PORT" -t monitor)
  if [[ -n "${MONITOR_BAUD:-}" ]]; then
    monitor_args+=(--monitor-baud "$MONITOR_BAUD")
  fi
  pio_run "${monitor_args[@]}"
}

package_firmware() {
  build
  source_dir="$FIRMWARE_DIR/.pio/build/$PIO_ENV"
  output_dir="$ROOT_DIR/artifacts/$PIO_ENV"
  mkdir -p "$output_dir"
  for artifact in bootloader.bin partitions.bin firmware.bin firmware.elf; do
    [[ -f "$source_dir/$artifact" ]] && cp "$source_dir/$artifact" "$output_dir/$artifact"
  done
  (
    cd "$output_dir"
    shasum -a 256 ./* 2>/dev/null > SHA256SUMS || true
  )
  echo "Packaged firmware in $output_dir"
}

list_envs() {
  (cd "$FIRMWARE_DIR" && "$PIO_BIN" project config --json-output 2>/dev/null || "$PIO_BIN" project config)
}

clean() {
  pio_run -t clean
}

require_command "$PIO_BIN"
[[ -d "$FIRMWARE_DIR" ]] || { echo "Firmware project not found: $FIRMWARE_DIR" >&2; exit 1; }

case "${1:-build}" in
  build|compile) build ;;
  flash|upload) flash ;;
  monitor) monitor ;;
  all) flash; monitor ;;
  package|artifacts) package_firmware ;;
  clean) clean ;;
  list) list_envs ;;
  help|-h|--help) usage ;;
  *) echo "Unknown command: $1" >&2; usage >&2; exit 2 ;;
esac

