#include "remote_update_service.h"

#include "update_service.h"

#include <ESPAsyncWebServer.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <mbedtls/base64.h>

namespace {

enum class RemoteState {
  IDLE,
  CHECK_QUEUED,
  CHECKING,
  AVAILABLE,
  APPLY_QUEUED,
  DOWNLOADING,
  FAILED
};

RemoteState remoteState = RemoteState::IDLE;
String manifestUrl;
String baseUrl;
String lastError;
TaskHandle_t workerTask = nullptr;
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;

constexpr uint32_t HTTP_TIMEOUT_MS = 10000;
constexpr size_t MAX_MANIFEST_BYTES = 2048;
constexpr size_t MAX_SIGNATURE_BYTES = 128;
constexpr size_t DOWNLOAD_CHUNK_BYTES = 4096;

#ifdef PROJ_REMOTE_UPDATE_ALLOW_HTTP
constexpr bool ALLOW_HTTP = true;
#else
constexpr bool ALLOW_HTTP = false;
#endif

const char* stateName(RemoteState state) {
  switch (state) {
    case RemoteState::IDLE: return "IDLE";
    case RemoteState::CHECK_QUEUED: return "CHECK_QUEUED";
    case RemoteState::CHECKING: return "CHECKING";
    case RemoteState::AVAILABLE: return "AVAILABLE";
    case RemoteState::APPLY_QUEUED: return "APPLY_QUEUED";
    case RemoteState::DOWNLOADING: return "DOWNLOADING";
    case RemoteState::FAILED: return "FAILED";
  }
  return "UNKNOWN";
}

bool validManifestUrl(const String& url) {
  if (url.length() < 16 || url.length() > 384) return false;
  if (url.startsWith("https://")) return url.endsWith("/manifest.json");
  if (url.startsWith("http://")) return ALLOW_HTTP && url.endsWith("/manifest.json");
  return false;
}

String deriveBaseUrl(const String& url) {
  const int slash = url.lastIndexOf('/');
  return slash > 7 ? url.substring(0, slash + 1) : String();
}

bool beginHttp(HTTPClient& http, WiFiClient& plain, WiFiClientSecure& secure,
               const String& url, String& error) {
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (url.startsWith("https://")) {
    // Update authenticity is provided by the signed manifest and firmware hash.
    // Proper CA validation is a separate TLS-hardening milestone.
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
  while (offset < static_cast<size_t>(declaredLength)) {
    const int available = stream->available();
    if (available <= 0) {
      if (!http.connected()) break;
      delay(1);
      continue;
    }
    const size_t wanted = min(static_cast<size_t>(available),
                              static_cast<size_t>(declaredLength) - offset);
    const int read = stream->readBytes(signature + offset, wanted);
    if (read <= 0) break;
    offset += static_cast<size_t>(read);
  }
  http.end();

  if (offset != static_cast<size_t>(declaredLength)) {
    error = "signature_read_incomplete";
    return false;
  }

  unsigned char encoded[256];
  size_t encodedLength = 0;
  const int result = mbedtls_base64_encode(encoded, sizeof(encoded), &encodedLength,
                                            signature, offset);
  if (result != 0 || encodedLength == 0) {
    error = "signature_base64_encode_failed";
    return false;
  }
  output = String(reinterpret_cast<char*>(encoded)).substring(0, encodedLength);
  return true;
}

void setFailed(const String& error) {
  portENTER_CRITICAL(&stateMux);
  lastError = error;
  remoteState = RemoteState::FAILED;
  workerTask = nullptr;
  portEXIT_CRITICAL(&stateMux);
}

void finishWorker(RemoteState state) {
  portENTER_CRITICAL(&stateMux);
  remoteState = state;
  workerTask = nullptr;
  portEXIT_CRITICAL(&stateMux);
}

void checkWorker(void*) {
  String localManifestUrl;
  portENTER_CRITICAL(&stateMux);
  remoteState = RemoteState::CHECKING;
  localManifestUrl = manifestUrl;
  portEXIT_CRITICAL(&stateMux);

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

  portENTER_CRITICAL(&stateMux);
  baseUrl = localBase;
  lastError = "";
  remoteState = RemoteState::AVAILABLE;
  workerTask = nullptr;
  portEXIT_CRITICAL(&stateMux);
  vTaskDelete(nullptr);
}

void applyWorker(void*) {
  String localBase;
  portENTER_CRITICAL(&stateMux);
  remoteState = RemoteState::DOWNLOADING;
  localBase = baseUrl;
  portEXIT_CRITICAL(&stateMux);

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

  const auto expected = FirmwarePackageVerifier::metadata();
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
  if (workerTask != nullptr) {
    error = "worker_busy";
    return false;
  }
  BaseType_t result = xTaskCreatePinnedToCore(function, name, 8192, nullptr, 1,
                                              &workerTask, 0);
  if (result != pdPASS) {
    workerTask = nullptr;
    error = "worker_create_failed";
    return false;
  }
  return true;
}

}  // namespace

namespace RemoteFirmwareUpdate {

void begin() {
  remoteState = RemoteState::IDLE;
  manifestUrl = "";
  baseUrl = "";
  lastError = "";
  workerTask = nullptr;
}

String statusJson() {
  portENTER_CRITICAL(&stateMux);
  const RemoteState state = remoteState;
  const String error = lastError;
  const String url = manifestUrl;
  portEXIT_CRITICAL(&stateMux);

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

    String error;
    portENTER_CRITICAL(&stateMux);
    const bool busy = workerTask != nullptr || remoteState == RemoteState::CHECKING ||
                      remoteState == RemoteState::DOWNLOADING;
    if (!busy) {
      manifestUrl = url;
      baseUrl = "";
      lastError = "";
      remoteState = RemoteState::CHECK_QUEUED;
    }
    portEXIT_CRITICAL(&stateMux);
    if (busy || !startWorker(checkWorker, "ota-check", error)) {
      if (!error.length()) error = "remote_update_busy";
      request->send(409, "application/json", "{\"error\":\"" + error + "\"}");
      return;
    }
    request->send(202, "application/json", statusJson());
  });

  server.on("/api/update/apply", HTTP_POST, [](AsyncWebServerRequest* request) {
    String error;
    portENTER_CRITICAL(&stateMux);
    const bool available = remoteState == RemoteState::AVAILABLE && workerTask == nullptr;
    if (available) remoteState = RemoteState::APPLY_QUEUED;
    portEXIT_CRITICAL(&stateMux);

    if (!available) {
      request->send(409, "application/json", "{\"error\":\"remote_update_not_available\"}");
      return;
    }
    if (!startWorker(applyWorker, "ota-apply", error)) {
      setFailed(error);
      request->send(500, "application/json", statusJson());
      return;
    }
    request->send(202, "application/json", statusJson());
  });
}

}  // namespace RemoteFirmwareUpdate
