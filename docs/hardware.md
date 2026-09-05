# Hardware notes

## Board and module

The board in use was purchased as a **NodeMCU-32S IoT board with Wi-Fi/Bluetooth, 38 pins and CP2102**, using an **ESP-WROOM-32** module.

The PlatformIO board registry on `kpnote` contains the exact board definition:

```text
nodemcu-32s   ESP32   240MHz   4MB   320KB   NodeMCU-32S
```

The project therefore uses `board = nodemcu-32s` rather than generic `esp32dev`.

## Direct probe results

The connected board was probed through `/dev/ttyUSB0` with esptool and reported:

- ESP32-D0WD-V3
- revision v3.0
- Wi-Fi + Bluetooth
- dual core + LP core
- 240 MHz capability
- 40 MHz crystal
- 4 MB external flash
- 3.3 V flash voltage

The USB bridge is a Silicon Labs CP2102/CP210x (`VID:PID 10c4:ea60`) handled by Linux driver `cp210x`.

## Electrical rules

ESP32 GPIO logic is **3.3 V**. Do not feed 5 V directly into GPIOs.

### Input-only GPIOs

- GPIO34
- GPIO35
- GPIO36 / SENSOR_VP
- GPIO39 / SENSOR_VN

These cannot be used as outputs. Do not depend on standard internal pull-up/pull-down behavior on these pins.

### Flash-reserved GPIOs

Avoid GPIO6 through GPIO11. On ESP-WROOM-32 these are normally connected to the module SPI flash.

### Boot strapping GPIOs

Use these with care because their level during reset influences boot configuration:

- GPIO0
- GPIO2
- GPIO5
- GPIO12
- GPIO15

A peripheral connected to one of these pins must not force an unsafe boot level.

### USB/UART0

- GPIO1 = UART0 TX
- GPIO3 = UART0 RX

They are used by the CP2102 serial path. Keep them available while USB upload/debug is important.

## Preferred buses

### I2C

- SDA: GPIO21
- SCL: GPIO22

### VSPI

- SCK: GPIO18
- MISO: GPIO19
- MOSI: GPIO23

Use this as the initial bus for TFT/touch unless the display wiring or performance requirements justify another mapping.

### HSPI alternative

- SCK: GPIO14
- MISO: GPIO12
- MOSI: GPIO13

GPIO12 is a strapping pin, so HSPI should not be adopted blindly for attached hardware.

## TFT/touch status

The user has an older color TFT module with resistive touch and microSD. Historical software clues point to:

- `TFT_eSPI` for display
- `XPT2046_Touchscreen` for resistive touch
- likely ILI9488 / ILI9486 / ILI9341 family display controller

The exact TFT display controller and CS/DC/RST/touch CS wiring are not confirmed yet. Do not bake those pin assignments into the base firmware until the module is identified.
