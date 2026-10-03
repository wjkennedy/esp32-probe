# ESP Probe

ESP Probe is a conservative hardware-discovery toolkit for ESP32-family
devices. It combines a Python USB-serial inventory tool, portable Arduino/
PlatformIO diagnostic firmware, board profiles, and a read-only MCP bridge.

The project is intended for devices you own or are authorized to modify. It
does not attempt to bypass locked firmware or protection mechanisms.

## Safety model

The default firmware and host tools are read-only with respect to the target:

- no flash erase or application-data writes;
- no arbitrary GPIO drive or voltage probing;
- no blind I²C/SPI scans;
- no Wi-Fi association in the baseline firmware;
- no automatic reset or bootloader entry from the discovery tool.

Board-specific active tests must be added behind an explicit profile and a
separate capability. A missing pin from a profile is not evidence that it is
safe to use.

## Install the host tools

```bash
cd esp_probe
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

The package depends on `pyserial`. On Linux, the account may need access to
the `dialout` group.

## Inventory and passive capture

List serial devices:

```bash
esp-usb-discovery --list
```

Capture boot/application output without transmitting to the target:

```bash
esp-usb-discovery \
  --port /dev/cu.usbserial-2130 \
  --baud 115200 \
  --seconds 3 \
  --json-out cyd-report.json
```

The optional `--at-probe` sends exactly one `AT\r\n` and is disabled by
default. Use it only with hardware you own or are authorized to test.

## Build, flash, and monitor firmware

PlatformIO is required. The repository-local cache defaults to `.pio-home` so
it does not depend on a writable global PlatformIO directory.

The default environment targets the classic ESP32 CYD 2.4″ profile:

```bash
./build.sh build
```

Flash a specific board only after explicitly identifying its serial port:

```bash
PORT=/dev/cu.usbserial-2130 ./build.sh flash
PORT=/dev/cu.usbserial-2130 ./build.sh monitor
```

Other commands:

```bash
./build.sh list
./build.sh package
./build.sh clean
```

Select another PlatformIO environment with `PIO_ENV`:

```bash
PIO_ENV=esp32-s3-devkitc-1 ./build.sh build
```

`package` writes build artifacts and SHA-256 checksums under
`artifacts/<environment>/`.

## Current probe firmware

The firmware emits newline-delimited JSON. On boot it reports:

- chip model, revision, core count, CPU frequency, and SDK version;
- reset reason;
- flash size, speed, mode, and JEDEC ID fields;
- heap, sketch, and PSRAM runtime data;
- eFuse base MAC and current Wi-Fi state/RSSI;
- advertised capabilities.

For `esp32-cyd-024`, it additionally initializes the documented CYD display
path and renders a small status screen. The known 2.4″ profile uses display
SPI GPIO 12/13/14, CS 15, DC 2, backlight 27, touch IRQ 36, and touch CS 33.
The firmware reports display initialization separately from positive controller
readback because some CYD variants do not wire display MISO for reads.

Firmware source and build details are in
[`firmware/esp_probe`](firmware/esp_probe/README.md). Board data lives in
[`profiles/`](profiles/).

## MCP query bridge

The host-side bridge exposes the USB-connected probe as read-only MCP tools over
stdio. It does not provision Wi-Fi or add an HTTP service to the board.

Run it directly from the checkout:

```bash
python -m esp_usb_discovery.mcp_server \
  --port /dev/cu.usbserial-2130 \
  --profile cyd-esp32-2432s024
```

After installing the package, the equivalent entrypoint is:

```bash
esp-probe-mcp \
  --port /dev/cu.usbserial-2130 \
  --profile cyd-esp32-2432s024
```

Available tools:

- `device.get_inventory`
- `device.get_capabilities`
- `device.get_boot_capture`
- `cyd.get_display_status`
- `cyd.read_flash_id`
- `device.get_gpio_map`

See [`docs/mcp-bridge.md`](docs/mcp-bridge.md) for transport and safety
details.

## Validated CYD 2.4″ result

The connected CYD test device at `/dev/cu.usbserial-2130` has reported:

```text
ESP32-D0WD-V3, revision 3, dual-core, 240 MHz
4 MiB flash, DIO mode, 40 MHz
No PSRAM
~345 KiB free heap
JEDEC ID 0x164068, manufacturer field 0x16
```

The display initialization path runs successfully. The controller readback was
`0x0`, so the current report correctly marks the controller as not positively
detected rather than guessing. This is the next hardware-specific item to
resolve before touch and bus discovery.

## Development roadmap

1. Validate CYD display configuration across 2.4″ and 2.8″ variants.
2. Add profile-gated XPT2046 touch identification/readout.
3. Add SD presence and metadata checks on documented SD pins.
4. Add I²C discovery only on known CYD pins and only when explicitly enabled.
5. Add T-Display S3 and LoRa board profiles.
6. Consider an ESP-side MCP/HTTP transport only after Wi-Fi provisioning,
   authentication, and network exposure are designed.

The full safety and profile model is documented in
[`docs/diagnostic-firmware.md`](docs/diagnostic-firmware.md).
