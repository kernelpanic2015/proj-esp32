#pragma once

#include <stdint.h>

namespace RuntimeCore {

enum class RuntimeEventType : uint16_t {
  ComponentStateChanged = 100,
  ComponentHealthChanged = 101
};

}  // namespace RuntimeCore
