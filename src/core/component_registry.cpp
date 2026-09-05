#include "core/component_registry.h"

#include <string.h>

namespace RuntimeCore {

bool ComponentRegistry::add(Component& component) {
  if (count_ >= MAX_COMPONENTS || find(component.id())) return false;
  components_[count_++] = &component;
  return true;
}

bool ComponentRegistry::beginAll() {
  bool ok = true;
  for (size_t i = 0; i < count_; ++i) {
    if (!components_[i]->begin()) ok = false;
  }
  return ok;
}

Component* ComponentRegistry::at(size_t index) const {
  return index < count_ ? components_[index] : nullptr;
}

Component* ComponentRegistry::find(const char* id) const {
  if (!id) return nullptr;
  for (size_t i = 0; i < count_; ++i) {
    if (strcmp(components_[i]->id(), id) == 0) return components_[i];
  }
  return nullptr;
}

String ComponentRegistry::statusJson() const {
  String json = "{\"count\":" + String(count_) + ",\"components\":[";
  for (size_t i = 0; i < count_; ++i) {
    if (i) json += ',';
    Component* c = components_[i];
    json += "{\"id\":\"" + String(c->id()) + "\",";
    json += "\"state\":\"" + String(c->stateName()) + "\",";
    json += "\"health\":" + healthJson(c->health()) + "}";
  }
  json += "]}";
  return json;
}

}  // namespace RuntimeCore
