from pathlib import Path

# Add a tiny shared restart service so every intentional software reboot can
# clear the DoubleResetDetector marker first. Hardware/manual resets still
# participate in DRD normally.
Path('include/restart_service.h').write_text('''#pragma once\n\nnamespace RestartService {\n\nusing BeforeRestartHook = void (*)();\n\nvoid setBeforeRestartHook(BeforeRestartHook hook);\nvoid restartNow();\n\n}  // namespace RestartService\n''')

Path('src/restart_service.cpp').write_text('''#include "restart_service.h"\n\n#include <Arduino.h>\n\nnamespace {\nRestartService::BeforeRestartHook beforeRestartHook = nullptr;\n}\n\nnamespace RestartService {\n\nvoid setBeforeRestartHook(BeforeRestartHook hook) {\n  beforeRestartHook = hook;\n}\n\nvoid restartNow() {\n  if (beforeRestartHook) {\n    beforeRestartHook();\n  }\n  ESP.restart();\n}\n\n}  // namespace RestartService\n''')

p = Path('src/main.cpp')
s = p.read_text()
if '#include "restart_service.h"' not in s:
    s = s.replace('#include "configuration_store.h"\n', '#include "configuration_store.h"\n#include "restart_service.h"\n', 1)
s = s.replace('ESP.restart();', 'RestartService::restartNow();')
needle = '''  drd = new DoubleResetDetector(ProjectConfig::DOUBLE_RESET_TIMEOUT_SECONDS,\n                                ProjectConfig::DOUBLE_RESET_STORAGE_ADDRESS);\n'''
replacement = needle + '''  RestartService::setBeforeRestartHook([]() {\n    if (drd) drd->stop();\n  });\n'''
if 'RestartService::setBeforeRestartHook' not in s:
    if needle not in s:
        raise SystemExit('DRD construction anchor not found')
    s = s.replace(needle, replacement, 1)
p.write_text(s)

p = Path('src/update_service.cpp')
s = p.read_text()
if '#include "restart_service.h"' not in s:
    s = s.replace('#include "update_service.h"\n', '#include "update_service.h"\n#include "restart_service.h"\n', 1)
s = s.replace('ESP.restart();', 'RestartService::restartNow();')
p.write_text(s)

# Advance only controlled test profiles. Default identity remains the last
# promoted baseline until the new code passes physical validation.
p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.26\\"\n    -DPROJ_FW_BUILD=27', '-DPROJ_FW_VERSION=\\"0.1.28\\"\n    -DPROJ_FW_BUILD=29')
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.26-remote-test\\"\n    -DPROJ_FW_BUILD=27', '-DPROJ_FW_VERSION=\\"0.1.28-remote-test\\"\n    -DPROJ_FW_BUILD=29')
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.27\\"\n    -DPROJ_FW_BUILD=28', '-DPROJ_FW_VERSION=\\"0.1.29\\"\n    -DPROJ_FW_BUILD=30')
p.write_text(s)

print('STAGE7A_DRD_FIX_PATCHED')
