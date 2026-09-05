#pragma once

#include <Arduino.h>
#include "core/component.h"

namespace RuntimeCore {

class ComponentRegistry {
 public:
  static constexpr size_t MAX_COMPONENTS = 24;

  bool add(Component& component);
  bool beginAll();
  size_t size() const { return count_; }
  Component* at(size_t index) const;
  Component* find(const char* id) const;
  String statusJson() const;

 private:
  Component* components_[MAX_COMPONENTS] = {};
  size_t count_ = 0;
};

}  // namespace RuntimeCore
