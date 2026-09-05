# External MQTT broker

The project can use an external RabbitMQ broker through MQTT.

Development policy:
- prefer MQTT over TLS on port 8883;
- keep credentials only in local `include/secrets.h` (gitignored);
- do not commit passwords to this repository;
- ESP32 publishes under `lab/proj-esp32/<device-id>/...`;
- backend/agents may later use AMQP against the same RabbitMQ instance.

Credentials and endpoint details are intentionally omitted from Git.
