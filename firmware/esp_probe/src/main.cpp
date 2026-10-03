#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include "esp_system.h"
#include "rom/spi_flash.h"

#ifdef ESP_PROBE_CYD
#include <TFT_eSPI.h>
#endif

// Safe baseline probe: it reports facts exposed by the runtime and does not
// configure, drive, or electrically test arbitrary pins.

#ifdef ESP_PROBE_CYD
static constexpr int CYD_BACKLIGHT_PIN = 27;
static TFT_eSPI display;
static uint32_t displayId = 0;
static bool displayReady = false;
#endif

static uint32_t flashJedecId() {
  const uint32_t raw = g_rom_flashchip.device_id;
  return ((raw & 0xff) << 16) | ((raw >> 16) & 0xff) | (raw & 0xff00);
}

static const char *resetReason(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "interrupt_watchdog";
    case ESP_RST_TASK_WDT: return "task_watchdog";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deep_sleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    default: return "unknown";
  }
}

static void printDocument(JsonDocument &doc) {
  serializeJson(doc, Serial);
  Serial.println();
}

static void emitHello() {
  JsonDocument doc;
  doc["type"] = "esp-probe";
  doc["version"] = 1;
  doc["capabilities"]["chip"] = true;
  doc["capabilities"]["flash"] = true;
  doc["capabilities"]["runtime"] = true;
  doc["capabilities"]["wifi"] = true;
#ifdef ESP_PROBE_CYD
  doc["capabilities"]["cyd_display"] = true;
  doc["capabilities"]["display_id_read"] = true;
#else
  doc["capabilities"]["cyd_display"] = false;
  doc["capabilities"]["display_id_read"] = false;
#endif
  doc["capabilities"]["gpio_read"] = false;
  doc["capabilities"]["gpio_drive"] = false;
  doc["capabilities"]["i2c_scan"] = false;
  doc["capabilities"]["spi_probe"] = false;
  printDocument(doc);
}

static void emitInventory() {
  JsonDocument doc;
  doc["type"] = "inventory";
  doc["chip"]["model"] = ESP.getChipModel();
  doc["chip"]["revision"] = ESP.getChipRevision();
  doc["chip"]["cores"] = ESP.getChipCores();
  doc["chip"]["cpu_mhz"] = ESP.getCpuFreqMHz();
  doc["chip"]["sdk"] = ESP.getSdkVersion();
  doc["chip"]["reset_reason"] = resetReason(esp_reset_reason());
  doc["flash"]["size_bytes"] = ESP.getFlashChipSize();
  doc["flash"]["speed_hz"] = ESP.getFlashChipSpeed();
  doc["flash"]["mode"] = (int)ESP.getFlashChipMode();
  doc["flash"]["jedec_id"] = flashJedecId();
  doc["flash"]["manufacturer_id"] = (flashJedecId() >> 16) & 0xff;
  doc["flash"]["device_id"] = flashJedecId() & 0xffff;
  doc["runtime"]["free_heap"] = ESP.getFreeHeap();
  doc["runtime"]["min_free_heap"] = ESP.getMinFreeHeap();
  doc["runtime"]["heap_size"] = ESP.getHeapSize();
  doc["runtime"]["sketch_size"] = ESP.getSketchSize();
  doc["runtime"]["free_sketch_space"] = ESP.getFreeSketchSpace();
  doc["runtime"]["psram_size"] = ESP.getPsramSize();
  doc["runtime"]["free_psram"] = ESP.getFreePsram();
  doc["identity"]["base_mac"] = ESP.getEfuseMac();
  doc["wifi"]["mode"] = (int)WiFi.getMode();
  if (WiFi.status() == WL_CONNECTED) {
    doc["wifi"]["connected"] = true;
    doc["wifi"]["rssi_dbm"] = WiFi.RSSI();
    doc["wifi"]["ssid"] = WiFi.SSID();
    doc["wifi"]["ip"] = WiFi.localIP().toString();
  } else {
    doc["wifi"]["connected"] = false;
  }
#ifdef ESP_PROBE_CYD
  doc["cyd_display"]["initialized"] = displayReady;
  doc["cyd_display"]["id"] = displayId;
  doc["cyd_display"]["controller_detected"] = displayId != 0 && displayId != 0xffffffff;
#endif
  printDocument(doc);
}

#ifdef ESP_PROBE_CYD
static void initializeCydDisplay() {
  pinMode(CYD_BACKLIGHT_PIN, OUTPUT);
  digitalWrite(CYD_BACKLIGHT_PIN, HIGH);
  display.init();
  display.setRotation(1);
  display.fillScreen(TFT_BLACK);
  display.setTextColor(TFT_WHITE, TFT_BLACK);
  display.setTextSize(2);
  display.drawString("ESP Probe", 8, 8);
  display.setTextSize(1);
  display.drawString(ESP.getChipModel(), 8, 38);
  display.drawString("CYD 2.4 / read-only", 8, 54);
  display.drawString("Serial: 115200", 8, 70);
  display.drawString("Inventory ready", 8, 86);
  displayId = display.readcommand32(0x04);
  display.drawString("Display ID: 0x" + String(displayId, HEX), 8, 110);
  display.drawString("Flash: " + String(ESP.getFlashChipSize() / (1024 * 1024)) + " MB", 8, 126);
  display.drawString("Heap: " + String(ESP.getFreeHeap() / 1024) + " KB", 8, 142);
  displayReady = true;
}
#endif

static void handleCommand(const String &command) {
  if (command == "hello") {
    emitHello();
  } else if (command == "inventory") {
    emitInventory();
  } else if (command == "help") {
    JsonDocument doc;
    doc["type"] = "help";
    doc["commands"][0] = "hello";
    doc["commands"][1] = "inventory";
    doc["commands"][2] = "help";
    printDocument(doc);
  } else if (command.length() > 0) {
    JsonDocument doc;
    doc["type"] = "error";
    doc["error"] = "unknown_command";
    doc["command"] = command;
    printDocument(doc);
  }
}

void setup() {
  Serial.begin(115200);
  delay(50);
#ifdef ESP_PROBE_CYD
  initializeCydDisplay();
#endif
  emitHello();
  emitInventory();
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    handleCommand(command);
  }
  delay(5);
}
