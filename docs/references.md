# References

## Hardware

- Retail board page / pinout / datasheet entry: https://www.usinainfo.com.br/esp32/esp32s-nodemcu-iot-com-wifi-e-bluetooth-38-pinos-com-cp2102-5346.html

## Firmware inspiration

- Tasmota documentation: https://tasmota.github.io/docs/
  - reference for the desired operational experience: provisioning, Web UI, console, MQTT and OTA
  - not used as the firmware base because this project needs custom C++ application logic and later TFT/touch integration

- MicroWebSrv2: https://github.com/jczic/MicroWebSrv2
  - useful architectural reference for web routes/WebSockets
  - not selected because it targets MicroPython/CPython while this firmware stays C++/Arduino

## Selected libraries

- Arduino FSM: https://github.com/jonblack/arduino-fsm
- ESP Double Reset Detector: https://github.com/khoih-prog/ESP_DoubleResetDetector
- WiFiManager: https://github.com/tzapu/WiFiManager
- ESPAsyncWebServer: https://github.com/ESP32Async/ESPAsyncWebServer
- AsyncTCP: https://github.com/ESP32Async/AsyncTCP
- WebSerial: https://github.com/ayushsharma82/WebSerial
- arduino-mqtt: https://github.com/256dpi/arduino-mqtt

## Display/touch references for the next phase

- XPT2046_Touchscreen: https://github.com/PaulStoffregen/XPT2046_Touchscreen
- TFT_eSPI: https://github.com/Bodmer/TFT_eSPI

The actual TFT controller and wiring remain to be identified before those dependencies are added to the active firmware.
