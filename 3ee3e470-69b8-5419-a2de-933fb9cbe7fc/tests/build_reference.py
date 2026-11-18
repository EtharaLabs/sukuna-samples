"""Render /opt/truth/audit_reference.md, the judged channel's reference, from /tests/oracle.json at verifier build."""
import json
from pathlib import Path

oracle = json.loads(Path("/tests/oracle.json").read_text())


def rows(key):
    value = oracle.get(key)
    if isinstance(value, dict):
        return list(value.values())
    return list(value or [])


md = ["# Thornby Field FSR-9 October response audit - reference",
      "",
      "Rendered at verifier build from tests/oracle.json. Counts are the reference totals the",
      "final account is judged against.",
      ""]
for key in ("findings", "corrections", "notices", "annotations"):
    md.append("- %s: %d" % (key, len(rows(key))))
cardinality = oracle.get("cardinality") or {}
if isinstance(cardinality, dict):
    for name in sorted(cardinality):
        md.append("- %s: %s" % (name, cardinality[name]))
ledger = oracle.get("close_ledger")
if ledger:
    md += ["", "## Period-close ledger", "", "```json",
           json.dumps(ledger, indent=2, sort_keys=True), "```"]
for key in ("findings", "corrections", "notices", "annotations"):
    md += ["", "## %s" % key.capitalize(), "", "```json",
           json.dumps(rows(key), indent=2, sort_keys=True), "```"]
final = oracle.get("final_message")
if final:
    md += ["", "## Reference closing note", "", str(final)]

Path("/opt/truth/audit_reference.md").write_text("\n".join(md) + "\n")
print("audit_reference.md", len("\n".join(md)), "chars")
