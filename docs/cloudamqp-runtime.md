# Cloud MQTT runtime notes

The production firmware should use MQTT over TLS. Development credentials must remain outside Git and be injected through the local build/runtime environment or `include/secrets.h` ignored by Git.
