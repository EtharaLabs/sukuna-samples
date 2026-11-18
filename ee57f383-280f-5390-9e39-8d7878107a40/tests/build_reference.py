"""Render /opt/truth/audit_reference.md, the judged channel's reference, from /tests/oracle.json at verifier build,
with the rule and table line that set each reference finding's limit."""
import json
from pathlib import Path

oracle = json.loads(Path("/tests/oracle.json").read_text())


def rows(key):
    value = oracle.get(key)
    if isinstance(value, dict):
        return list(value.values())
    return list(value or [])


md = ["# Keldford October drivers' hours and working time audit - reference",
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
# The rule and table line each edition sets a finding's limit by, read off the two editions of the code
# (wt7-edition-3.txt and wt7-edition-4.txt, sections 2 to 9), so the judged channel can check the
# rule-and-table line the note gives for every reference finding.
CITATIONS = {
    "DAILY_DRIVING": ("2.1", {"WT-7 Ed 3": "2a, row 1", "WT-7 Ed 4": "2a, row 1"}),
    "CONTINUOUS_DRIVING": ("3.1", {"WT-7 Ed 3": "3a, row 1", "WT-7 Ed 4": "3a, row 1"}),
    "NIGHT_WORK": ("4.1", {"WT-7 Ed 3": "4a, row 1", "WT-7 Ed 4": "4b, row 1"}),
    "BREAK_COMPOSITION": ("5.1", {"WT-7 Ed 3": "5a, row 2", "WT-7 Ed 4": "5b, row 2"}),
    "AVAILABILITY": ("6.1", {"WT-7 Ed 3": "6a, row 1", "WT-7 Ed 4": "6b, row 1"}),
    "ROLLING_WORKING_TIME": ("7.1", {"WT-7 Ed 3": "7a, row 1", "WT-7 Ed 4": "7b, row 1"}),
    "DAILY_REST": ("8.1", {"WT-7 Ed 3": "8a, row 1", "WT-7 Ed 4": "8a, row 1"}),
    "WEEKLY_REST": ("8.2", {"WT-7 Ed 3": "8a, row 2", "WT-7 Ed 4": "8a, row 2"}),
}
md += ["", "## Rule and table line per finding", ""]
for row in sorted(rows("findings"), key=lambda r: (r["DutyRef"], r["FindingType"])):
    rule, tables = CITATIONS[row["FindingType"]]
    md.append("- %s %s for %s: %s, rule %s, table %s" % (
        row["DutyRef"], row["FindingType"], row["Driver"], row["EditionApplied"], rule, tables[row["EditionApplied"]]))
final = oracle.get("final_message")
if final:
    md += ["", "## Reference closing note", "", str(final)]

Path("/opt/truth/audit_reference.md").write_text("\n".join(md) + "\n")
print("audit_reference.md", len("\n".join(md)), "chars")
