#pragma once

#include <stdint.h>

namespace FirmwareIdentity {

// Hardware family/profile. Update packages must match MODEL and
// HARDWARE_REVISION before they can be considered applicable.
constexpr char MODEL[] = "proj-esp32-35";
constexpr uint16_t HARDWARE_REVISION = 1;

// Human-readable version plus monotonic build used for update ordering.
constexpr char VERSION[] = "0.1.2";
constexpr uint32_t BUILD = 3;
constexpr char CHANNEL[] = "dev";

}  // namespace FirmwareIdentity
