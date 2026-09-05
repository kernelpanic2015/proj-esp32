#pragma once

// Canonical GPIO notes for the NodeMCU-32S / ESP-WROOM-32 used by this project.
// Logic level is 3.3 V. Do not apply 5 V to ESP32 GPIOs.

namespace BoardPins {

// Default I2C pins on the ESP32 Arduino core.
constexpr int I2C_SDA = 21;
constexpr int I2C_SCL = 22;

// VSPI bus: preferred starting point for TFT/touch experiments.
constexpr int VSPI_SCK  = 18;
constexpr int VSPI_MISO = 19;
constexpr int VSPI_MOSI = 23;

// HSPI alternate bus.
constexpr int HSPI_SCK  = 14;
constexpr int HSPI_MISO = 12;
constexpr int HSPI_MOSI = 13;

// UART0 is connected to the CP2102 USB bridge. Keep these free while using
// the serial console/upload path.
constexpr int UART0_TX = 1;
constexpr int UART0_RX = 3;

// Input-only GPIOs. They cannot drive outputs and do not provide normal
// internal pull-up/pull-down support.
constexpr int INPUT_ONLY[] = {34, 35, 36, 39};

// GPIO6..GPIO11 are normally used by the module's SPI flash. Do not use them
// as application GPIOs on this ESP-WROOM-32 board.
constexpr int FLASH_RESERVED[] = {6, 7, 8, 9, 10, 11};

// Strapping pins affect boot configuration. They can be used only when the
// attached peripheral cannot force an unsafe level during reset/boot.
constexpr int STRAPPING[] = {0, 2, 5, 12, 15};

}  // namespace BoardPins
