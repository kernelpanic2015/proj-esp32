#pragma once

namespace RestartService {

using BeforeRestartHook = void (*)();

void setBeforeRestartHook(BeforeRestartHook hook);
void restartNow();

}  // namespace RestartService
