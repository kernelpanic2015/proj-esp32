#include "remote_update_service.h"

#include "firmware_package_verifier.h"
#include "update_service.h"

#include <ESPAsyncWebServer.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <mbedtls/base64.h>

namespace {

enum class RemoteState {
  IDLE,
  CHECKING,
  AVAILABLE,
  DOWNLOADING,
  FAILED
};

RemoteState remoteState = RemoteState::IDLE;
String manifestUrl;
String baseUrl;
String lastError;
TaskHandle_t workerTask = nullptr;
SemaphoreHandle_t stateMutex = nullptr;

constexpr uint32_t HTTP_TIMEOUT_MS = 10000;
constexpr size_t MAX_MANIFEST_BYTES = 2048;
constexpr size_t MAX_SIGNATURE_BYTES = 128;
constexpr size_t DOWNLOAD_CHUNK_BYTES = 4096;

#ifdef PROJ_REMOTE_UPDATE_ALLOW_HTTP
constexpr bool ALLOW_HTTP = true;
#else
constexpr bool ALLOW_HTTP = false;
#endif

class StateLock {
 public:
  StateLock() : locked_(stateMutex && xSemaphoreTake(stateMutex, pdMS_TO_TICKS(250)) == pdTRUE) {}
  ~StateLock() { if (locked_) xSemaphoreGive(stateMutex); }
  bool locked() const { return locked_; }
 private:
  bool locked_;
};

const char* stateName(RemoteState state) {
  switch (state) {
    case RemoteState::IDLE: return "IDLE";
    case RemoteState::CHECKING: return "CHECKING";
    case RemoteState::AVAILABLE: return "AVAILABLE";
    case RemoteState::DOWNLOADING: return "DOWNLOADING";
    case RemoteState::FAILED: return "FAILED";
  }
  return "UNKNOWN";
}

bool validManifestUrl(const String& url) {
  if (url.length() < 16 || url.length() > 384 || !url.endsWith("/manifest.json")) {
    return false;
  }
  if (url.startsWith("https://")) return true;
  return ALLOW_HTTP && url.startsWith("http://");
}

String deriveBaseUrl(const String& url) {
  const int slash = url.lastIndexOf('/');
  return slash > 7 ? url.substring(0, slash + 1) : String();
}

bool beginHttp(HTTPClient& http, WiFiClient& plain, WiFiClientSecure& secure,
               const String& url, String& error) {
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (url.startsWith("https://")) {
    // The signed manifest authenticates update metadata and the signed SHA-256
    // binds the downloaded image. CA validation is hardened separately.
    secure.setInsecure();
    if (!http.begin(secure, url)) {
      error = "https_begin_failed";
      return false;
    }
    return true;
  }
  if (!ALLOW_HTTP) {
    error = "http_not_allowed";
    return false;
  }
  if (!http.begin(plain, url)) {
    error = "http_begin_failed";
    return false;
  }
  return true;
}

bool fetchText(const String& url, size_t maxBytes, String& output, String& error) {
  HTTPClient http;
  WiFiClient plain;
  WiFiClientSecure secure;
  if (!beginHttp(http, plain, secure, url, error)) return false;

  const int code = http.GET();
  if (code != HTTP_CODE_OK) {
    error = "http_status_" + String(code);
    http.end();
    return false;
  }

  const int length = http.getSize();
  if (length > 0 && static_cast<size_t>(length) > maxBytes) {
    error = "response_too_large";
    http.end();
    return false;
  }

  output = http.getString();
  http.end();
  if (output.length() == 0 || output.length() > maxBytes) {
    error = "response_size_invalid";
    return false;
  }
  return true;
}

bool fetchSignatureBase64(const String& url, String& output, String& error) {
  HTTPClient http;
  WiFiClient plain;
  WiFiClientSecure secure;
  if (!beginHttp(http, plain, secure, url, error)) return false;

  const int code = http.GET();
  if (code != HTTP_CODE_OK) {
    error = "signature_http_status_" + String(code);
    http.end();
    return false;
  }

  const int declaredLength = http.getSize();
  if (declaredLength <= 0 || declaredLength > static_cast<int>(MAX_SIGNATURE_BYTES)) {
    error = "signature_size_invalid";
    http.end();
    return false;
  }

  uint8_t signature[MAX_SIGNATURE_BYTES];
  size_t offset = 0;
  WiFiClient* stream = http.getStreamPtr();
  unsigned long lastProgress = millis();
  while (offset < static_cast<size_t>(declaredLength)) {
    const int available = stream->available();
    if (available <= 0) {
      if (!http.connected()) break;
      if (millis() - lastProgress > HTTP_TIMEOUT_MS) break;
      delay(1);
      continue;
    }
    const size_t wanted = min(static_cast<size_t>(available),
                              static_cast<size_t>(declaredLength) - offset);
    const int read = stream->readBytes(signature + offset, wanted);
    if (read <= 0) break;
    offset += static_cast<size_t>(read);
    lastProgress = millis();
  }
  http.end();

  if (offset != static_cast<size_t>(declaredLength)) {
    error = "signature_read_incomplete";
    return false;
  }

  unsigned char encoded[256];
  size_t encodedLength = 0;
  const int result = mbedtls_base64_encode(encoded, sizeof(encoded) - 1,
                                            &encodedLength, signature, offset);
  if (result != 0 || encodedLength == 0 || encodedLength >= sizeof(encoded)) {
    error = "signature_base64_encode_failed";
    return false;
  }
  encoded[encodedLength] = '\0';
  output = String(reinterpret_cast<char*>(encoded));
  return true;
}

void setFailed(const String& error) {
  StateLock lock;
  if (lock.locked()) {
    lastError = error;
    remoteState = RemoteState::FAILED;
    workerTask = nullptr;
  }
}

void finishWorker(RemoteState state) {
  StateLock lock;
  if (lock.locked()) {
    remoteState = state;
    workerTask = nullptr;
  }
}

void checkWorker(void*) {
  String localManifestUrl;
  {
    StateLock lock;
    if (!lock.locked()) {
      vTaskDelete(nullptr);
      return;
    }
    remoteState = RemoteState::CHECKING;
    localManifestUrl = manifestUrl;
  }

  if (WiFi.status() != WL_CONNECTED) {
    setFailed("wifi_not_connected");
    vTaskDelete(nullptr);
    return;
  }

  String error;
  String manifest;
  if (!fetchText(localManifestUrl, MAX_MANIFEST_BYTES, manifest, error)) {
    setFailed("manifest_" + error);
    vTaskDelete(nullptr);
    return;
  }

  const String localBase = deriveBaseUrl(localManifestUrl);
  if (!localBase.length()) {
    setFailed("manifest_base_url_invalid");
    vTaskDelete(nullptr);
    return;
  }

  String signatureBase64;
  if (!fetchSignatureBase64(localBase + "manifest.sig", signatureBase64, error)) {
    setFailed(error);
    vTaskDelete(nullptr);
    return;
  }

  if (!FirmwareUpdate::preparePackage(manifest, signatureBase64, error)) {
    setFailed("prepare_" + error);
    vTaskDelete(nullptr);
    return;
  }

  {
    StateLock lock;
    if (lock.locked()) {
      baseUrl = localBase;
      lastError = "";
      remoteState = RemoteState::AVAILABLE;
      workerTask = nullptr;
    }
  }
  vTaskDelete(nullptr);
}

void applyWorker(void*) {
  String localBase;
  {
    StateLock lock;
    if (!lock.locked()) {
      vTaskDelete(nullptr);
      return;
    }
    remoteState = RemoteState::DOWNLOADING;
    localBase = baseUrl;
  }

  if (WiFi.status() != WL_CONNECTED) {
    setFailed("wifi_not_connected");
    vTaskDelete(nullptr);
    return;
  }

  String error;
  HTTPClient http;
  WiFiClient plain;
  WiFiClientSecure secure;
  if (!beginHttp(http, plain, secure, localBase + "firmware.bin", error)) {
    setFailed("firmware_" + error);
    vTaskDelete(nullptr);
    return;
  }

  const int code = http.GET();
  if (code != HTTP_CODE_OK) {
    setFailed("firmware_http_status_" + String(code));
    http.end();
    vTaskDelete(nullptr);
    return;
  }

  const FirmwarePackageVerifier::Metadata expected = FirmwarePackageVerifier::metadata();
  const int declaredLength = http.getSize();
  if (declaredLength <= 0 || static_cast<size_t>(declaredLength) != expected.size) {
    setFailed("firmware_content_length_mismatch");
    http.end();
    vTaskDelete(nullptr);
    return;
  }

  if (!FirmwareUpdate::beginPreparedInstall(error)) {
    setFailed("install_begin_" + error);
    http.end();
    vTaskDelete(nullptr);
    return;
  }

  uint8_t buffer[DOWNLOAD_CHUNK_BYTES];
  size_t total = 0;
  WiFiClient* stream = http.getStreamPtr();
  unsigned long lastProgress = millis();

  while (total < expected.size) {
    const size_t remaining = expected.size - total;
    const int available = stream->available();
    if (available <= 0) {
      if (!http.connected()) break;
      if (millis() - lastProgress > HTTP_TIMEOUT_MS) {
        error = "firmware_read_timeout";
        break;
      }
      delay(1);
      continue;
    }

    const size_t wanted = min(min(static_cast<size_t>(available), sizeof(buffer)), remaining);
    const int read = stream->readBytes(buffer, wanted);
    if (read <= 0) {
      error = "firmware_read_failed";
      break;
    }
    if (!FirmwareUpdate::writePreparedChunk(buffer, static_cast<size_t>(read), error)) {
      break;
    }
    total += static_cast<size_t>(read);
    lastProgress = millis();
    delay(0);
  }
  http.end();

  if (error.length()) {
    setFailed(error);
    vTaskDelete(nullptr);
    return;
  }
  if (total != expected.size) {
    setFailed("firmware_read_incomplete");
    vTaskDelete(nullptr);
    return;
  }
  if (!FirmwareUpdate::finishPreparedInstall(error)) {
    setFailed("install_finish_" + error);
    vTaskDelete(nullptr);
    return;
  }

  finishWorker(RemoteState::IDLE);
  vTaskDelete(nullptr);
}

bool startWorker(TaskFunction_t function, const char* name, String& error) {
  StateLock lock;
  if (!lock.locked()) {
    error = "state_lock_timeout";
    return false;
  }
  if (workerTask != nullptr) {
    error = "worker_busy";
    return false;
  }

  TaskHandle_t task = nullptr;
  const BaseType_t result = xTaskCreatePinnedToCore(function, name, 8192, nullptr, 1,
                                                    &task, 0);
  if (result != pdPASS) {
    error = "worker_create_failed";
    return false;
  }
  workerTask = task;
  return true;
}

}  // namespace

namespace RemoteFirmwareUpdate {

void begin() {
  if (!stateMutex) stateMutex = xSemaphoreCreateMutex();
  StateLock lock;
  if (lock.locked()) {
    remoteState = RemoteState::IDLE;
    manifestUrl = "";
    baseUrl = "";
    lastError = "";
    workerTask = nullptr;
  }
}

String statusJson() {
  RemoteState state = RemoteState::FAILED;
  String error = "state_lock_timeout";
  String url;
  {
    StateLock lock;
    if (lock.locked()) {
      state = remoteState;
      error = lastError;
      url = manifestUrl;
    }
  }

  String json = "{";
  json += "\"state\":\"" + String(stateName(state)) + "\",";
  json += "\"error\":\"" + error + "\",";
  json += "\"manifest_url\":\"" + url + "\",";
  json += "\"http_allowed\":" + String(ALLOW_HTTP ? "true" : "false");
  json += "}";
  return json;
}

void registerRoutes(AsyncWebServer& server) {
  server.on("/api/update/remote/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  server.on("/api/update/check", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("manifest_url", true)) {
      request->send(400, "application/json", "{\"error\":\"manifest_url_required\"}");
      return;
    }

    String url = request->getParam("manifest_url", true)->value();
    url.trim();
    if (!validManifestUrl(url)) {
      request->send(400, "application/json", "{\"error\":\"manifest_url_invalid\"}");
      return;
    }

    {
      StateLock lock;
      if (!lock.locked()) {
        request->send(503, "application/json", "{\"error\":\"state_lock_timeout\"}");
        return;
      }
      if (workerTask != nullptr || remoteState == RemoteState::CHECKING ||
          remoteState == RemoteState::DOWNLOADING) {
        request->send(409, "application/json", "{\"error\":\"remote_update_busy\"}");
        return;
      }
      manifestUrl = url;
      baseUrl = "";
      lastError = "";
      remoteState = RemoteState::IDLE;
    }

    String error;
    if (!startWorker(checkWorker, "ota-check", error)) {
      setFailed(error);
      request->send(500, "application/json", statusJson());
      return;
    }
    request->send(202, "application/json", statusJson());
  });

  server.on("/api/update/apply", HTTP_POST, [](AsyncWebServerRequest* request) {
    {
      StateLock lock;
      if (!lock.locked()) {
        request->send(503, "application/json", "{\"error\":\"state_lock_timeout\"}");
        return;
      }
      if (remoteState != RemoteState::AVAILABLE || workerTask != nullptr) {
        request->send(409, "application/json", "{\"error\":\"remote_update_not_available\"}");
        return;
      }
    }

    String error;
    if (!startWorker(applyWorker, "ota-apply", error)) {
      setFailed(error);
      request->send(500, "application/json", statusJson());
      return;
    }
    request->send(202, "application/json", statusJson());
  });
}

}  // namespace RemoteFirmwareUpdate
