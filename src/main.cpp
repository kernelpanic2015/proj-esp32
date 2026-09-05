#include <Arduino.h>
void setup(){Serial.begin(115200);delay(800);Serial.println("ESP32_SMOKE_BOOT_OK");}
void loop(){Serial.println("ESP32_SMOKE_HEARTBEAT_OK");delay(1000);}
