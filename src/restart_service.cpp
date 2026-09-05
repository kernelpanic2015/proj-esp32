#include "restart_service.h"

#include <Arduino.h>

namespace {
RestartService::BeforeRestartHook beforeRestartHook = nullptr;
}

namespace RestartService {

void setBeforeRestartHook(BeforeRestartHook hook) {
  beforeRestartHook = hook;
}

void restartNow() {
  if (beforeRestartHook) {
    beforeRestartHook();
  }
  ESP.restart();
}

}  // namespace RestartService
