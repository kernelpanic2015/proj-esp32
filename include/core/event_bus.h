#pragma once

#include <Arduino.h>

namespace RuntimeCore {

struct Event {
  uint16_t type = 0;
  uint32_t atMs = 0;
  int32_t value = 0;
  char source[24] = {};
};

using EventHandler = void (*)(const Event& event);

class EventBus {
 public:
  static constexpr size_t QUEUE_SIZE = 24;
  static constexpr size_t MAX_HANDLERS = 12;

  bool subscribe(EventHandler handler);
  bool post(uint16_t type, const char* source, int32_t value = 0);
  size_t process(size_t maxEvents = 8);
  size_t pending() const { return count_; }
  uint32_t dropped() const { return dropped_; }

 private:
  Event queue_[QUEUE_SIZE] = {};
  EventHandler handlers_[MAX_HANDLERS] = {};
  size_t head_ = 0;
  size_t tail_ = 0;
  size_t count_ = 0;
  size_t handlerCount_ = 0;
  uint32_t dropped_ = 0;
};

}  // namespace RuntimeCore
