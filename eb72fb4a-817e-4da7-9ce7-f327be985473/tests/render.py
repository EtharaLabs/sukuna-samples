"""Render the judge's two inputs: the reference (at verifier build) and the run's own state (at verify time).

python render.py reference <plan.json> <out.md>
python render.py state <out.md>        (reads the same paths as test_outputs.py)
"""
import json
import sys

RULE = {"SHIFT": "Appendix A maximum shift for the local start band and ward-assignment count (3.1)",
        "EXTENSION": "Appendix A maximum plus the site manager's extension allowance of the revision (4.1, 4.3)",
        "REST": "minimum rest: the preceding duty period, not less than 11:00 (5.1), plus any extension under Revision 7 (5.3)",
        "HOURS_7D": "60:00 in any 7 consecutive days (6.1)", "HOURS_14D": "110:00 in any 14 consecutive days (6.1)",
        "HOURS_28D": "190:00 in any 28 consecutive days (6.1)"}
SOURCES = {"TS": "ward timesheet photograph over the shift-actuals clock-out time and ward-assignment count (8.1)",
           "SEA": "shift extension authorisation over the actuals extension flag (8.2)",
           "BL": "site manager's bleep-log note over the roster and actuals for a call-in, transfer or where on-call was served (8.3)"}


def reference(plan_path, out):
    plan = json.load(open(plan_path))
    lines = ["# Reference: October 2026 roster-period safe staffing audit", "",
             "Revision rule: each shift's revision is decided by its start time in UK local time (BST, UTC+1, until 01:00 UTC on 25 October 2026, then GMT); Revision 6 before 00:00 local on 15 October 2026, Revision 7 from then (1.1, 1.2).", ""]
    for f in sorted(plan["findings"], key=lambda x: x["key"]):
        ev = ", ".join(f"{e} ({SOURCES[e.split('-')[0]]})" for e in f["evidence"]) or "none: the shift-actuals record stood"
        lines.append(f"- {f['staff']} {f['key_ref']} {f['limit_type']}: rule {RULE[f['limit_type']]}; {f['edition']}; limit {f['limit_min']}, actual {f['actual_min']}, excess {f['excess_min']} min; evidence {ev}.")
    t = plan["triggers"]
    lines += ["", "Sources overridden in this audit:",
              "- ward timesheet photographs over the shift-actuals clock-out time and ward-assignment count;",
              "- extension authorisations over the actuals extension flag, and an extension without a filed authorisation treated as none;",
              "- bleep-log notes over the roster for a call-in with a transfer and for on-call served on site;",
              "- the workforce systems over last week's roster export;",
              "- the record over the staff side representative's channel messages and the draft local agreement, which have no standing.",
              "", f"During the run: after the first close the actuals for {t['a']['duty']} were corrected (clock-out {t['a']['on_blocks_before']} to {t['a']['on_blocks_after']}), "
              f"so the period had to be reopened and restated; staff {t['b']['staff']}'s register address changed after the twelfth finding was written"
              + (f", and staff {t['e']['staff']}'s at the first close" if t.get("e") else "")
              + (f"; at the second close the actuals for {t['f']['duty']} moved (clock-out {t['f']['on_blocks_before']} to {t['f']['on_blocks_after']}), adding a finding"
                 if t.get("f") else "")
              + (f"; extension authorisation {t['unsigned']['report_id']} for {t['unsigned']['duty']} was never signed, so that extension does not stand"
                 if t.get("unsigned") else "")
              + (f"; and after the twentieth finding was written the actuals for {t['c']['duty']} changed (clock-out {t['c']['on_blocks_before']} to "
                 f"{t['c']['on_blocks_after']}), adding a finding." if t.get("c") else ".")]
    try:
        from generator import docs
        lines += ["", "Appendix A, Revision 6:", docs._table("Rev 6"), "Appendix A, Revision 7:", docs._table("Rev 7"),
                  f"Extension allowance: Revision 6 two hours, Revision 7 ninety minutes. Revision 7 adds the extension to the following rest."]
    except ImportError:
        pass
    open(out, "w").write("\n".join(lines) + "\n")


def state(out):
    import test_outputs as t
    run = t.run()
    lines = ["# The run's end state", "", "## Finding records (title, then properties)"]
    for f in sorted(run.live, key=run.key):
        lines.append(f"- {f['_title']} | Reference {f.get('Reference')} | {f.get('Edition')} | limit {f.get('Limit min')}, actual {f.get('Actual min')}, "
                     f"excess {f.get('Excess min')} | evidence {f.get('Evidence') or 'none'}")
    lines += ["", f"## Period close: status {run.close.get('Status')}, findings {run.close.get('Findings')}, excess total {run.close.get('Excess total min')}",
              "", f"## Notices sent ({len(run.sent)})"]
    for m in run.sent:
        lines += ["", f"### To {m.get('to_addr')}: {m.get('subject')}", str(m.get("body", ""))]
    open(out, "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    reference(sys.argv[2], sys.argv[3]) if sys.argv[1] == "reference" else state(sys.argv[2])
