#include "core/event_bus.h"

#include <stdio.h>
#include <string.h>

namespace RuntimeCore {

bool EventBus::subscribe(EventHandler handler) {
  if (!handler || handlerCount_ >= MAX_HANDLERS) return false;
  for (size_t i = 0; i < handlerCount_; ++i) {
    if (handlers_[i] == handler) return true;
  }
  handlers_[handlerCount_++] = handler;
  return true;
}

bool EventBus::post(uint16_t type, const char* source, int32_t value) {
  if (count_ >= QUEUE_SIZE) {
    ++dropped_;
    return false;
  }

  Event& event = queue_[tail_];
  event.type = type;
  event.atMs = millis();
  event.value = value;
  snprintf(event.source, sizeof(event.source), "%s", source ? source : "");
  tail_ = (tail_ + 1) % QUEUE_SIZE;
  ++count_;
  return true;
}

size_t EventBus::process(size_t maxEvents) {
  size_t processed = 0;
  while (count_ && processed < maxEvents) {
    Event event = queue_[head_];
    head_ = (head_ + 1) % QUEUE_SIZE;
    --count_;
    for (size_t i = 0; i < handlerCount_; ++i) handlers_[i](event);
    ++processed;
  }
  return processed;
}

}  // namespace RuntimeCore
