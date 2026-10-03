# ESP Probe firmware

This is the first portable diagnostic firmware for devices you own or are
authorized to modify. It uses the Arduino core so the same application can be
built for classic ESP32 and ESP32-S3 boards while the host tool is developed.

## Build and flash

Install PlatformIO, connect a board in its documented download mode, and use a
board-specific environment:

```sh
pio run -e esp32dev
pio run -e esp32dev -t upload
pio device monitor -b 115200
```

The S3 environment is `esp32-s3-devkitc-1`. Do not select an environment just
because its connector fits: select one matching the actual chip family and
flash configuration.

## Serial protocol

The firmware emits newline-delimited JSON. On boot it sends `hello` followed by
`inventory`. Commands are plain text lines:

```text
hello
inventory
help
```

The baseline intentionally does not write flash, change CPU frequency, connect
to Wi-Fi, scan I2C, claim SPI pins, or configure/read/drive arbitrary GPIOs.
Those operations require a board profile with explicit pins, voltage limits,
and ownership notes. A future host command should check the advertised
capabilities before requesting them.

