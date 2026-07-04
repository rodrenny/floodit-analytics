"""Contract guard: every mart model must set contract.enforced.

dbt_project.yml already applies +contract.enforced to the marts tree; this
guard makes CI fail if anyone removes or overrides that config, instead of
silently shipping an uncontracted public interface.
"""

import json
import sys
from pathlib import Path

MANIFEST = Path("dbt/target/manifest.json")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    violations = []
    marts = 0
    for node in manifest["nodes"].values():
        if node["resource_type"] != "model":
            continue
        if "marts" not in Path(node["path"]).parts:
            continue
        marts += 1
        contract = node["config"].get("contract") or {}
        if not contract.get("enforced"):
            violations.append(node["name"])
    if violations:
        print("FAIL — marts without contract.enforced:")
        for name in violations:
            print(f"  - {name}")
        return 1
    print(f"OK — {marts} mart model(s), all contract-enforced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
