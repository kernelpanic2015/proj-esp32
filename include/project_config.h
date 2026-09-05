#pragma once

#include <stdint.h>

namespace ProjectConfig {

constexpr char DEVICE_HOSTNAME[] = "proj-esp32";
constexpr char CONFIG_PORTAL_SSID[] = "proj-esp32-setup";
constexpr uint16_t CONFIG_PORTAL_TIMEOUT_SECONDS = 180;

// Initial MQTT target. It can be changed later to a provisioned/persisted
// setting. The first milestone is to validate the complete MQTT path.
constexpr char MQTT_HOST[] = "kpnote.local";
constexpr uint16_t MQTT_PORT = 1883;
constexpr char MQTT_TOPIC_ROOT[] = "lab/proj-esp32";
constexpr uint32_t MQTT_RECONNECT_INTERVAL_MS = 5000;
constexpr uint32_t HEARTBEAT_INTERVAL_MS = 10000;

constexpr uint8_t DOUBLE_RESET_TIMEOUT_SECONDS = 10;
constexpr uint32_t DOUBLE_RESET_STORAGE_ADDRESS = 0;

}  // namespace ProjectConfig
