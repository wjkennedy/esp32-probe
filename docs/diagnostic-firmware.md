# Diagnostic firmware roadmap

The project has two layers:

1. The Python host tool inventories USB serial adapters and passively captures
   boot/application output.
2. The custom firmware reports facts that are only available after code is
   running on the ESP: chip revision, reset reason, flash geometry exposed by
   the runtime, heap/PSRAM, identity, and Wi-Fi state/RSSI.

## Safety model

Every diagnostic operation should advertise a capability and its side effects.
The default profile is read-only and must not assume that a GPIO is unused,
3.3 V tolerant, connected to an ADC, or safe to toggle. This matters for CYDs
with displays/touch, T-Display S3 peripherals, LoRa radios, battery-backed
boards, and products with external pull-ups or level shifters.

Suggested capability classes:

- `read_only`: chip, reset, flash/runtime metadata, MAC, Wi-Fi state/RSSI.
- `passive_bus`: inspect a bus only when pins and electrical levels are known.
- `active_test`: drive a pin, scan I2C, or transmit radio frames; requires an
  explicit board profile and user confirmation.
- `destructive`: erase/write/update/clock changes; keep out of the discovery
  command path and require a separate, conspicuous workflow.

## Board profiles

A profile should be data, not scattered conditionals. At minimum it should
contain the board name, chip family, logic voltage, flash/PSRAM expectations,
known display/touch/LoRa pins, safe GPIOs, reserved GPIOs, I2C/SPI mappings,
and whether each test is electrically safe. Unknown pins remain unknown.

Initial profiles to add after the generic probe is validated:

- generic ESP32-WROOM development board
- CYD variants, with display/touch profiles kept separate; the first two
  evidence-backed profiles are in [`profiles/`](../profiles/)
- LilyGO T-Display S3 variants
- LoRa boards, with radio pins and antenna constraints documented

## Next implementation increments

1. Add host-side JSONL protocol support and correlate a firmware report with
   the USB port/boot capture.
2. Add a profile loader and a `capabilities` command.
3. Add passive, profile-gated I2C/SPI metadata checks without claiming buses by
   default.
4. Add explicit, opt-in GPIO tests that require the user to disconnect or
   identify attached peripherals.
5. Add separate, documented tooling for standard ROM bootloader metadata reads.

Overclocking, flash writes, erases, and locked-firmware handling belong outside
the baseline probe. They are board- and hardware-specific and should never be
silently triggered by inventory or discovery.
