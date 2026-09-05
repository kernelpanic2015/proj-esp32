from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel, old, new):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor in {rel}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

replace_once(
    "docs/README.md",
    "- [x] Stage 7A transactional ConfigurationStore: apply/reject/reboot/rollback/OTA persistence physically validated\n",
    "- [x] Stage 7A transactional ConfigurationStore: apply/reject/reboot/rollback/OTA persistence physically validated\n"
    "- [~] Stage 7B minimal RuleEngine + virtual I/O implementation; physical proof pending\n",
)

replace_once(
    "docs/README.md",
    "Stage 6 core runtime is validated and Stage 7A transactional configuration is physically validated. Configuration revision 3 survived reboot, rollback and signed OTA. Intentional software restart now clears the DRD marker before reboot so it cannot masquerade as a human double-reset request. **Stage 7B — the smallest virtual-input/virtual-output local rule model — is next.**\n",
    "Stage 6 core runtime is validated and Stage 7A transactional configuration is physically validated. Configuration revision 3 survived reboot, rollback and signed OTA. Intentional software restart now clears the DRD marker before reboot so it cannot masquerade as a human double-reset request. **Stage 7B is in progress:** the minimal hardware-independent hysteresis RuleEngine and controlled virtual input/output path are implemented for physical proof.\n",
)

replace_once(
    "README.md",
    "**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Apply/reject/reboot/rollback/OTA persistence was physically proven. Intentional software reboots clear the DRD marker first. Stage 7B now starts with virtual input/output and minimal local-rule semantics; RuleEngine does not access GPIO.\n",
    "**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Apply/reject/reboot/rollback/OTA persistence was physically proven. Intentional software reboots clear the DRD marker first. **Stage 7B is in progress:** a minimal hardware-independent hysteresis RuleEngine and controlled virtual input/output path are implemented for proof; RuleEngine returns desired state and never accesses GPIO.\n",
)

print("STAGE7B_FINISH_PATCHED")
