// Arduino-ESP32 defines verifyRollbackLater() as a weak hook. By default it
// returns false, so initArduino() immediately validates a PENDING_VERIFY image
// before setup() runs. We override it so proj-esp32 owns the validation window
// in FirmwareUpdate::tick().
extern "C" bool verifyRollbackLater() {
  return true;
}
