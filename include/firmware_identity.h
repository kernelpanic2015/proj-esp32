#pragma once

#include <stdint.h>

#ifndef PROJ_FW_MODEL
#define PROJ_FW_MODEL "proj-esp32-35"
#endif

#ifndef PROJ_HW_REVISION
#define PROJ_HW_REVISION 1
#endif

#ifndef PROJ_FW_VERSION
#define PROJ_FW_VERSION "0.1.17"
#endif

#ifndef PROJ_FW_BUILD
#define PROJ_FW_BUILD 18
#endif

#ifndef PROJ_FW_CHANNEL
#define PROJ_FW_CHANNEL "dev"
#endif

namespace FirmwareIdentity {

// Hardware family/profile. Update packages must match MODEL and
// HARDWARE_REVISION before they can be considered applicable.
constexpr char MODEL[] = PROJ_FW_MODEL;
constexpr uint16_t HARDWARE_REVISION = PROJ_HW_REVISION;

// Human-readable version plus monotonic build used for update ordering.
// Compile-time overrides are used only by controlled test/release profiles.
constexpr char VERSION[] = PROJ_FW_VERSION;
constexpr uint32_t BUILD = PROJ_FW_BUILD;
constexpr char CHANNEL[] = PROJ_FW_CHANNEL;

}  // namespace FirmwareIdentity
