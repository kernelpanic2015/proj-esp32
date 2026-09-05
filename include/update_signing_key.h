#pragma once

namespace FirmwareUpdateTrust {

// Public ECDSA P-256 key used to verify signed update manifests.
// The corresponding private key must remain outside the repository/device.
// Source of truth for the public PEM is keys/update-signing-public.pem.
constexpr char PUBLIC_KEY_PEM[] =
    "-----BEGIN PUBLIC KEY-----\n"
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE5lcKI4aBFMjURcN/cLtIuWxYPeyO\n"
    "+NEnSlJlSYCsGzAwXb+9/JKzxoGTuiS4ONAoQIhbYtcJ6mRUPUAIS+rAyg==\n"
    "-----END PUBLIC KEY-----\n";

}  // namespace FirmwareUpdateTrust
