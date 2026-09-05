#include "firmware_package_verifier.h"

#include "firmware_identity.h"
#include "update_signing_key.h"

#include <ArduinoJson.h>
#include <ctype.h>
#include <mbedtls/base64.h>
#include <mbedtls/pk.h>
#include <mbedtls/sha256.h>
#include <string.h>

namespace {

FirmwarePackageVerifier::Metadata preparedMetadata;

bool safeToken(const char* value, size_t maxLength) {
  if (!value) return false;
  const size_t length = strlen(value);
  if (length == 0 || length > maxLength) return false;

  for (size_t i = 0; i < length; ++i) {
    const unsigned char c = static_cast<unsigned char>(value[i]);
    if (!(isalnum(c) || c == '.' || c == '_' || c == '-' || c == '+')) {
      return false;
    }
  }
  return true;
}

int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

bool parseSha256(const char* value, uint8_t output[32]) {
  if (!value || strlen(value) != 64) return false;
  for (size_t i = 0; i < 32; ++i) {
    const int high = hexNibble(value[i * 2]);
    const int low = hexNibble(value[i * 2 + 1]);
    if (high < 0 || low < 0) return false;
    output[i] = static_cast<uint8_t>((high << 4) | low);
  }
  return true;
}

bool sha256Bytes(const uint8_t* data, size_t length, uint8_t output[32]) {
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);

  bool ok = mbedtls_sha256_starts_ret(&ctx, 0) == 0;
  if (ok) ok = mbedtls_sha256_update_ret(&ctx, data, length) == 0;
  if (ok) ok = mbedtls_sha256_finish_ret(&ctx, output) == 0;

  mbedtls_sha256_free(&ctx);
  return ok;
}

bool verifySignature(const String& manifestJson,
                     const String& signatureBase64,
                     String& error) {
  String encoded = signatureBase64;
  encoded.trim();
  if (encoded.length() == 0 || encoded.length() > 192) {
    error = "signature_encoding_invalid";
    return false;
  }

  uint8_t signature[128];
  size_t signatureLength = 0;
  const int decodeResult = mbedtls_base64_decode(
      signature, sizeof(signature), &signatureLength,
      reinterpret_cast<const unsigned char*>(encoded.c_str()), encoded.length());
  if (decodeResult != 0 || signatureLength == 0) {
    error = "signature_base64_invalid";
    return false;
  }

  uint8_t manifestHash[32];
  if (!sha256Bytes(reinterpret_cast<const uint8_t*>(manifestJson.c_str()),
                   manifestJson.length(), manifestHash)) {
    error = "manifest_hash_failed";
    return false;
  }

  mbedtls_pk_context publicKey;
  mbedtls_pk_init(&publicKey);
  int result = mbedtls_pk_parse_public_key(
      &publicKey,
      reinterpret_cast<const unsigned char*>(FirmwareUpdateTrust::PUBLIC_KEY_PEM),
      strlen(FirmwareUpdateTrust::PUBLIC_KEY_PEM) + 1);

  if (result == 0) {
    result = mbedtls_pk_verify(&publicKey, MBEDTLS_MD_SHA256,
                               manifestHash, sizeof(manifestHash),
                               signature, signatureLength);
  }

  mbedtls_pk_free(&publicKey);

  if (result != 0) {
    error = "manifest_signature_invalid";
    return false;
  }
  return true;
}

}  // namespace

namespace FirmwarePackageVerifier {

void clear() {
  preparedMetadata = Metadata();
}

bool prepared() {
  return preparedMetadata.valid;
}

const Metadata& metadata() {
  return preparedMetadata;
}

bool prepare(const String& manifestJson,
             const String& signatureBase64,
             String& error) {
  clear();
  error = "";

  if (manifestJson.length() == 0 || manifestJson.length() > 2048) {
    error = "manifest_size_invalid";
    return false;
  }

  if (!verifySignature(manifestJson, signatureBase64, error)) {
    return false;
  }

  StaticJsonDocument<1024> document;
  const DeserializationError jsonError = deserializeJson(document, manifestJson);
  if (jsonError) {
    error = "manifest_json_invalid";
    return false;
  }

  if (!document["schema"].is<uint32_t>() ||
      !document["model"].is<const char*>() ||
      !document["hardware_revision"].is<uint16_t>() ||
      !document["version"].is<const char*>() ||
      !document["build"].is<uint32_t>() ||
      !document["channel"].is<const char*>() ||
      !document["size"].is<uint32_t>() ||
      !document["sha256"].is<const char*>() ||
      !document["file"].is<const char*>()) {
    error = "manifest_fields_invalid";
    return false;
  }

  const uint32_t schema = document["schema"].as<uint32_t>();
  const char* model = document["model"].as<const char*>();
  const uint16_t hardwareRevision = document["hardware_revision"].as<uint16_t>();
  const char* version = document["version"].as<const char*>();
  const uint32_t build = document["build"].as<uint32_t>();
  const char* channel = document["channel"].as<const char*>();
  const uint32_t size = document["size"].as<uint32_t>();
  const char* sha256Hex = document["sha256"].as<const char*>();
  const char* file = document["file"].as<const char*>();

  if (schema != 1) {
    error = "manifest_schema_unsupported";
    return false;
  }
  if (!model || strcmp(model, FirmwareIdentity::MODEL) != 0) {
    error = "manifest_model_mismatch";
    return false;
  }
  if (hardwareRevision != FirmwareIdentity::HARDWARE_REVISION) {
    error = "manifest_hardware_mismatch";
    return false;
  }
  if (!safeToken(version, 48)) {
    error = "manifest_version_invalid";
    return false;
  }
  if (build <= FirmwareIdentity::BUILD) {
    error = "manifest_build_not_newer";
    return false;
  }
  if (!channel || strcmp(channel, FirmwareIdentity::CHANNEL) != 0) {
    error = "manifest_channel_mismatch";
    return false;
  }
  if (size == 0) {
    error = "manifest_firmware_size_invalid";
    return false;
  }
  if (!file || strcmp(file, "firmware.bin") != 0) {
    error = "manifest_file_invalid";
    return false;
  }

  uint8_t expectedHash[32];
  if (!parseSha256(sha256Hex, expectedHash)) {
    error = "manifest_sha256_invalid";
    return false;
  }

  preparedMetadata.valid = true;
  preparedMetadata.schema = schema;
  preparedMetadata.model = model;
  preparedMetadata.hardwareRevision = hardwareRevision;
  preparedMetadata.version = version;
  preparedMetadata.build = build;
  preparedMetadata.channel = channel;
  preparedMetadata.size = size;
  preparedMetadata.sha256Hex = sha256Hex;
  memcpy(preparedMetadata.sha256, expectedHash, sizeof(expectedHash));
  return true;
}

}  // namespace FirmwarePackageVerifier
