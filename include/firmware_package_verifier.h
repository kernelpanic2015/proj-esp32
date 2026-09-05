#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

namespace FirmwarePackageVerifier {

struct Metadata {
  bool valid = false;
  uint32_t schema = 0;
  uint16_t hardwareRevision = 0;
  uint32_t build = 0;
  size_t size = 0;
  String model;
  String version;
  String channel;
  String sha256Hex;
  uint8_t sha256[32] = {0};
};

// Verifies the base64-encoded DER ECDSA signature over the exact manifest
// bytes, parses the signed metadata and checks applicability to this device.
bool prepare(const String& manifestJson,
             const String& signatureBase64,
             String& error);

void clear();
bool prepared();
const Metadata& metadata();

}  // namespace FirmwarePackageVerifier
