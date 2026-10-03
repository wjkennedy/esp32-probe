# MCP bridge

`esp-probe-mcp` exposes the read-only ESP Probe over MCP stdio. It keeps the
device on USB serial, so it does not provision Wi-Fi or add an HTTP attack
surface to the diagnostic firmware.

Start it with the port for the connected board:

```sh
esp-probe-mcp \
  --port /dev/cu.usbserial-2130 \
  --profile cyd-esp32-2432s024
```

Configure an MCP client to launch that command. The server supports
`initialize`, `ping`, `tools/list`, and `tools/call`. Its tools are read-only:

- `device.get_inventory`
- `device.get_capabilities`
- `device.get_boot_capture`
- `cyd.get_display_status`
- `cyd.read_flash_id`
- `device.get_gpio_map`

The bridge sends only `hello` and `inventory` commands to the current firmware.
It never writes flash, resets the board, drives arbitrary GPIOs, scans buses,
or changes Wi-Fi state. Profile GPIO data is returned from the repository’s
JSON profile files and is not presented as proof that an unlisted pin is safe.

