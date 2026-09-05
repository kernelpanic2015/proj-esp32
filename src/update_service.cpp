#include "update_service.h"
#include "firmware_package_verifier.h"
#include "ota_state_names.h"

#include <ESPAsyncWebServer.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>
#include <string.h>

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
bool updateSessionOpen = false;
bool uploadHashActive = false;
mbedtls_sha256_context uploadHashContext;

constexpr uint32_t REBOOT_DELAY_MS = 750;
constexpr uint32_t VALIDATION_MIN_MS = 10000;
constexpr uint32_t VALIDATION_TIMEOUT_MS = 30000;
constexpr uint32_t MIN_HEAP_FOR_VALID_IMAGE = 60000;

#ifdef PROJ_OTA_TEST_FORCE_VALIDATION_FAILURE
constexpr bool FORCE_VALIDATION_FAILURE = true;
#else
constexpr bool FORCE_VALIDATION_FAILURE = false;
#endif

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

void clearUploadHash() {
  if (uploadHashActive) {
    mbedtls_sha256_free(&uploadHashContext);
    uploadHashActive = false;
  }
}

bool beginUploadHash() {
  clearUploadHash();
  mbedtls_sha256_init(&uploadHashContext);
  if (mbedtls_sha256_starts_ret(&uploadHashContext, 0) != 0) {
    mbedtls_sha256_free(&uploadHashContext);
    return false;
  }
  uploadHashActive = true;
  return true;
}

bool updateUploadHash(const uint8_t* data, size_t len) {
  return uploadHashActive &&
         mbedtls_sha256_update_ret(&uploadHashContext, data, len) == 0;
}

bool finishUploadHash(uint8_t output[32]) {
  if (!uploadHashActive) return false;
  const bool ok = mbedtls_sha256_finish_ret(&uploadHashContext, output) == 0;
  mbedtls_sha256_free(&uploadHashContext);
  uploadHashActive = false;
  return ok;
}

void failUpdate(const String& reason) {
  if (updateSessionOpen) {
    Update.abort();
    updateSessionOpen = false;
  }
  clearUploadHash();
  lastError = reason;
  setState(UpdateState::FAILED);
}

String partitionLabel(const esp_partition_t* partition) {
  return partition ? String(partition->label) : String("unknown");
}

String runningImageStateName() {
  const esp_partition_t* running = esp_ota_get_running_partition();
  esp_ota_img_states_t imageState;
  if (!running || esp_ota_get_state_partition(running, &imageState) != ESP_OK) {
    return "UNAVAILABLE";
  }
  return String(otaImageStateName(imageState));
}

bool canPreparePackage() {
  return updateState == UpdateState::IDLE ||
         updateState == UpdateState::VALID ||
         updateState == UpdateState::FAILED;
}

String updatePage() {
  String page = "<!doctype html><html><head><meta charset='utf-8'>";
  page += "<meta name='viewport' content='width=device-width,initial-scale=1'>";
  page += "<title>proj-esp32 signed firmware update</title></head><body>";
  page += "<h1>Signed firmware update</h1>";
  page += "<p>The manifest signature and firmware SHA-256 are verified on the ESP32 before the new image is selected for boot.</p>";
  page += "<p><a href='/api/version'>Current version</a> | <a href='/api/update/status'>Update status</a></p>";
  page += "<form id='updateForm'>";
  page += "<label>Manifest <input id='manifest' type='file' accept='.json,application/json' required></label><br>";
  page += "<label>Signature <input id='signature' type='file' accept='.sig,application/octet-stream' required></label><br>";
  page += "<label>Firmware <input id='firmware' type='file' accept='.bin,application/octet-stream' required></label><br>";
  page += "<button type='submit'>Verify and install</button></form><pre id='result'></pre>";
  page += "<script>";
  page += "const form=document.getElementById('updateForm'),out=document.getElementById('result');";
  page += "form.addEventListener('submit',async(e)=>{e.preventDefault();out.textContent='Preparing signed package...';";
  page += "try{const mf=document.getElementById('manifest').files[0],sf=document.getElementById('signature').files[0],fw=document.getElementById('firmware').files[0];";
  page += "const manifest=await mf.text();const sigBytes=new Uint8Array(await sf.arrayBuffer());let binary='';for(const b of sigBytes)binary+=String.fromCharCode(b);const signature=btoa(binary);";
  page += "const prep=new URLSearchParams();prep.set('manifest',manifest);prep.set('signature',signature);";
  page += "const pr=await fetch('/api/update/prepare',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:prep.toString()});const pt=await pr.text();out.textContent='prepare: '+pr.status+' '+pt;if(!pr.ok)return;";
  page += "const fd=new FormData();fd.append('firmware',fw);const ur=await fetch('/api/update/upload',{method:'POST',body:fd});const ut=await ur.text();out.textContent+='\\nupload: '+ur.status+' '+ut;}catch(err){out.textContent+='\\nerror: '+err;}});";
  page += "</script></body></html>";
  return page;
}

}  // namespace

namespace FirmwareUpdate {

void begin(bool criticalStorageReady) {
  FirmwarePackageVerifier::clear();
  clearUploadHash();
  updateSessionOpen = false;
  receivedBytes = 0;

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
  } else {
    lastError = "";
  }
  setState(UpdateState::IDLE);
}

String statusJson() {
  const esp_partition_t* running = esp_ota_get_running_partition();
  const esp_partition_t* boot = esp_ota_get_boot_partition();
  const esp_partition_t* nextUpdate = esp_ota_get_next_update_partition(nullptr);
  const bool packagePrepared = FirmwarePackageVerifier::prepared();

  String json = "{";
  json += "\"state\":\"" + String(stateName(updateState)) + "\",";
  json += "\"received_bytes\":" + String(static_cast<unsigned long>(receivedBytes)) + ",";
  json += "\"error\":\"" + lastError + "\",";
  json += "\"running_partition\":\"" + partitionLabel(running) + "\",";
  json += "\"boot_partition\":\"" + partitionLabel(boot) + "\",";
  json += "\"next_update_partition\":\"" + partitionLabel(nextUpdate) + "\",";
  json += "\"image_state\":\"" + runningImageStateName() + "\",";
  json += "\"package_prepared\":" + String(packagePrepared ? "true" : "false") + ",";
  if (packagePrepared) {
    const auto& package = FirmwarePackageVerifier::metadata();
    json += "\"candidate_version\":\"" + package.version + "\",";
    json += "\"candidate_build\":" + String(package.build) + ",";
    json += "\"candidate_size\":" + String(static_cast<unsigned long>(package.size)) + ",";
  }
  json += "\"validation_test_forced_failure\":" + String(FORCE_VALIDATION_FAILURE ? "true" : "false") + ",";
#ifdef CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE
  json += "\"rollback_enabled\":true";
#else
  json += "\"rollback_enabled\":false";
#endif
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

  server.on("/api/update/prepare", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!canPreparePackage()) {
      request->send(409, "application/json", statusJson());
      return;
    }
    if (!request->hasParam("manifest", true) ||
        !request->hasParam("signature", true)) {
      lastError = "package_prepare_missing_fields";
      request->send(400, "application/json", statusJson());
      return;
    }

    const String manifest = request->getParam("manifest", true)->value();
    const String signature = request->getParam("signature", true)->value();
    String verificationError;
    if (!FirmwarePackageVerifier::prepare(manifest, signature, verificationError)) {
      lastError = "package_prepare_" + verificationError;
      request->send(400, "application/json", statusJson());
      return;
    }

    const auto& package = FirmwarePackageVerifier::metadata();
    const esp_partition_t* nextUpdate = esp_ota_get_next_update_partition(nullptr);
    if (!nextUpdate || package.size > nextUpdate->size) {
      FirmwarePackageVerifier::clear();
      lastError = "package_firmware_too_large";
      request->send(400, "application/json", statusJson());
      return;
    }

    lastError = "";
    request->send(200, "application/json", statusJson());
  });

  server.on(
      "/api/update/upload", HTTP_POST,
      [](AsyncWebServerRequest* request) {
        const bool accepted = updateState == UpdateState::PENDING_REBOOT;
        request->send(accepted ? 200 : 400, "application/json", statusJson());
      },
      [](AsyncWebServerRequest* request, const String& filename, size_t index,
         uint8_t* data, size_t len, bool final) {
        (void)request;
        (void)filename;

        if (index == 0) {
          receivedBytes = 0;
          lastError = "";

          if (!FirmwarePackageVerifier::prepared()) {
            failUpdate("signed_package_not_prepared");
            return;
          }

          const auto& package = FirmwarePackageVerifier::metadata();
          const esp_partition_t* nextUpdate = esp_ota_get_next_update_partition(nullptr);
          if (!nextUpdate || package.size > nextUpdate->size) {
            failUpdate("package_firmware_too_large");
            return;
          }

          if (!beginUploadHash()) {
            failUpdate("firmware_hash_begin_failed");
            return;
          }

          setState(UpdateState::RECEIVING);
          if (!Update.begin(package.size, U_FLASH)) {
            failUpdate("update_begin_failed_" + String(Update.getError()));
            return;
          }
          updateSessionOpen = true;
        }

        if (updateState != UpdateState::RECEIVING) {
          return;
        }

        const auto& package = FirmwarePackageVerifier::metadata();
        if (receivedBytes + len > package.size) {
          failUpdate("firmware_size_exceeded");
          return;
        }

        if (len > 0) {
          if (!updateUploadHash(data, len)) {
            failUpdate("firmware_hash_update_failed");
            return;
          }

          const size_t written = Update.write(data, len);
          if (written != len) {
            failUpdate("update_write_failed_" + String(Update.getError()));
            return;
          }
          receivedBytes += written;
        }

        if (final) {
          setState(UpdateState::FINALIZING);

          if (receivedBytes != package.size) {
            failUpdate("firmware_size_mismatch");
            return;
          }

          uint8_t actualHash[32];
          if (!finishUploadHash(actualHash)) {
            failUpdate("firmware_hash_finish_failed");
            return;
          }
          if (memcmp(actualHash, package.sha256, sizeof(actualHash)) != 0) {
            failUpdate("firmware_sha256_mismatch");
            return;
          }

          if (!Update.end(true)) {
            failUpdate("update_end_failed_" + String(Update.getError()));
            return;
          }
          updateSessionOpen = false;
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
  const bool localHealthOk = !FORCE_VALIDATION_FAILURE &&
                             criticalStorageReady &&
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
    lastError = FORCE_VALIDATION_FAILURE ? "forced_boot_validation_failure" : "boot_validation_failed";
    setState(UpdateState::ROLLBACK);
    esp_ota_mark_app_invalid_rollback_and_reboot();
  }
}

}  // namespace FirmwareUpdate
