# Cloud MQTT test plan

Validate the external RabbitMQ MQTT endpoint from `kpnote` first, then switch the ESP32 firmware to TLS credentials stored only in local `include/secrets.h`, build, upload, and validate publish/subscribe from both sides.
