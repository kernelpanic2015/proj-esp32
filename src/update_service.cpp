#include "update_service.h"

#include <ESPAsyncWebServer.h>
#include <Update.h>
#include <esp_ota_ops.h>

namespace {

enum class UpdateState {
  IDLE,
  RECEIVING,
  FINALIZING,
  PENDING_REBOOT,
  PENDING_VERIFY,
  VALID,
  FAILED,
  ROLLBACK
};

UpdateState updateState = UpdateState::IDLE;
String lastError;
size_t receivedBytes = 0;
unsigned long stateSinceMs = 0;

constexpr uint32_t REBOOT_DELAY_MS = 750;
constexpr uint32_t VALIDATION_MIN_MS = 10000;
constexpr uint32_t VALIDATION_TIMEOUT_MS = 30000;
constexpr uint32_t MIN_HEAP_FOR_VALID_IMAGE = 60000;

const char* stateName(UpdateState state) {
  switch (state) {
    case UpdateState::IDLE: return "IDLE";
    case UpdateState::RECEIVING: return "RECEIVING";
    case UpdateState::FINALIZING: return "FINALIZING";
    case UpdateState::PENDING_REBOOT: return "PENDING_REBOOT";
    case UpdateState::PENDING_VERIFY: return "PENDING_VERIFY";
    case UpdateState::VALID: return "VALID";
    case UpdateState::FAILED: return "FAILED";
    case UpdateState::ROLLBACK: return "ROLLBACK";
  }
  return "UNKNOWN";
}

void setState(UpdateState next) {
  updateState = next;
  stateSinceMs = millis();
}

void failUpdate(const String& reason) {
  lastError = reason;
  setState(UpdateState::FAILED);
}

String updatePage() {
  String page = "<!doctype html><html><head><meta charset='utf-8'>";
  page += "<meta name='viewport' content='width=device-width,initial-scale=1'>";
  page += "<title>proj-esp32 firmware update</title></head><body>";
  page += "<h1>Firmware update</h1>";
  page += "<p>This development endpoint writes a firmware .bin to the inactive OTA slot.</p>";
  page += "<p><a href='/api/version'>Current version</a> | <a href='/api/update/status'>Update status</a></p>";
  page += "<form method='post' action='/api/update/upload' enctype='multipart/form-data'>";
  page += "<input type='file' name='firmware' accept='.bin,application/octet-stream' required>";
  page += "<button type='submit'>Upload firmware</button></form>";
  page += "</body></html>";
  return page;
}

}  // namespace

namespace FirmwareUpdate {

void begin(bool criticalStorageReady) {
  const esp_partition_t* running = esp_ota_get_running_partition();
  esp_ota_img_states_t imageState;

  if (running && esp_ota_get_state_partition(running, &imageState) == ESP_OK &&
      imageState == ESP_OTA_IMG_PENDING_VERIFY) {
    lastError = "";
    setState(UpdateState::PENDING_VERIFY);
    return;
  }

  if (!criticalStorageReady) {
    lastError = "critical_storage_not_ready";
  }
  setState(UpdateState::IDLE);
}

String statusJson() {
  String json = "{";
  json += "\"state\":\"" + String(stateName(updateState)) + "\",";
  json += "\"received_bytes\":" + String(receivedBytes) + ",";
  json += "\"error\":\"" + lastError + "\",";
  json += "\"running_partition\":\"";
  const esp_partition_t* running = esp_ota_get_running_partition();
  json += running ? String(running->label) : String("unknown");
  json += "\"";
  json += "}";
  return json;
}

void registerRoutes(AsyncWebServer& server) {
  server.on("/api/update/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  server.on("/update", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "text/html", updatePage());
  });

  server.on(
      "/api/update/upload", HTTP_POST,
      [](AsyncWebServerRequest* request) {
        const bool accepted = updateState == UpdateState::PENDING_REBOOT;
        request->send(accepted ? 200 : 500, "application/json", statusJson());
      },
      [](AsyncWebServerRequest* request, const String& filename, size_t index,
         uint8_t* data, size_t len, bool final) {
        (void)request;
        (void)filename;

        if (index == 0) {
          receivedBytes = 0;
          lastError = "";
          setState(UpdateState::RECEIVING);
          if (!Update.begin(UPDATE_SIZE_UNKNOWN, U_FLASH)) {
            failUpdate("update_begin_failed_" + String(Update.getError()));
            return;
          }
        }

        if (updateState != UpdateState::RECEIVING) {
          return;
        }

        if (len > 0) {
          const size_t written = Update.write(data, len);
          if (written != len) {
            failUpdate("update_write_failed_" + String(Update.getError()));
            return;
          }
          receivedBytes += written;
        }

        if (final) {
          setState(UpdateState::FINALIZING);
          if (!Update.end(true)) {
            failUpdate("update_end_failed_" + String(Update.getError()));
            return;
          }
          setState(UpdateState::PENDING_REBOOT);
        }
      });
}

void tick(bool criticalStorageReady) {
  if (updateState == UpdateState::PENDING_REBOOT &&
      millis() - stateSinceMs >= REBOOT_DELAY_MS) {
    ESP.restart();
    return;
  }

  if (updateState != UpdateState::PENDING_VERIFY) {
    return;
  }

  const uint32_t elapsed = millis() - stateSinceMs;
  const bool localHealthOk = criticalStorageReady &&
                             ESP.getFreeHeap() >= MIN_HEAP_FOR_VALID_IMAGE;

  if (localHealthOk && elapsed >= VALIDATION_MIN_MS) {
    const esp_err_t result = esp_ota_mark_app_valid_cancel_rollback();
    if (result == ESP_OK) {
      lastError = "";
      setState(UpdateState::VALID);
    } else {
      failUpdate("mark_valid_failed_" + String(static_cast<int>(result)));
    }
    return;
  }

  if (!localHealthOk && elapsed >= VALIDATION_TIMEOUT_MS) {
    lastError = "boot_validation_failed";
    setState(UpdateState::ROLLBACK);
    esp_ota_mark_app_invalid_rollback_and_reboot();
  }
}

}  // namespace FirmwareUpdate
