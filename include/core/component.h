#pragma once

#include <Arduino.h>
#include "core/component_health.h"

namespace RuntimeCore {

// A component owns behavior/state. TaskScheduler owns when its work is due.
// FSMs inside components decide whether requested work is legal in that state.
class Component {
 public:
  virtual ~Component() = default;
  virtual const char* id() const = 0;
  virtual bool begin() = 0;
  virtual const char* stateName() const = 0;
  virtual ComponentHealth health() const = 0;
};

}  // namespace RuntimeCore
