"""Render the judge's two inputs: the reference (at verifier build) and the run's own state (at verify time).

python render.py reference <plan.json> <out.md>
python render.py state <out.md>        (reads the same paths as test_outputs.py)
"""
import json
import sys

RULE = {"FDP": "Appendix A maximum FDP for the local report band and sector count (7.3)",
        "DISCRETION": "Appendix A maximum plus the commander's discretion allowance of the revision (7.4.1, 7.4.3)",
        "REST": "minimum rest: the preceding duty period, not less than 12:00 at base or 10:00 away (7.5.1), plus any extension under Revision 14 (7.5.3)",
        "DUTY_7D": "60:00 in any 7 consecutive days (7.6.1)", "DUTY_14D": "110:00 in any 14 consecutive days (7.6.1)",
        "DUTY_28D": "190:00 in any 28 consecutive days (7.6.1)"}
SOURCES = {"TL": "technical-log page over the duty-actuals on-blocks time and sector count (7.8.1)",
           "CDR": "commander's discretion report over the actuals discretion flag (7.8.2)",
           "VN": "duty-control call-log entry over the roster and actuals for a call-out, positioning or where a standby was served (7.8.3)"}


def reference(plan_path, out):
    plan = json.load(open(plan_path))
    lines = ["# Reference: September 2026 block audit", "",
             "Revision rule: each duty's revision is decided by its report time in base local time (UTC+1); Revision 13 before 00:00 local on 15 September 2026, Revision 14 from then (7.1.1, 7.1.2).", ""]
    for f in sorted(plan["findings"], key=lambda x: x["key"]):
        ev = ", ".join(f"{e} ({SOURCES[e.split('-')[0]]})" for e in f["evidence"]) or "none: the duty-actuals record stood"
        lines.append(f"- {f['staff']} {f['key_ref']} {f['limit_type']}: rule {RULE[f['limit_type']]}; {f['edition']}; limit {f['limit_min']}, actual {f['actual_min']}, excess {f['excess_min']} min; evidence {ev}.")
    t = plan["triggers"]
    lines += ["", "Sources overridden in this audit:",
              "- technical-log pages over the duty-actuals on-blocks time and sector count;",
              "- discretion reports over the actuals discretion flag, and an extension without a filed report treated as none;",
              "- duty-control call-log entries over the roster for a call-out with positioning and for a standby served at the airport;",
              "- the crew systems over last week's roster export;",
              "- the record over the branch representative's channel messages and the draft side letter, which have no standing.",
              "", f"During the run: after the first close the actuals for {t['a']['duty']} were corrected (on-blocks {t['a']['on_blocks_before']} to {t['a']['on_blocks_after']}), "
              f"so the block had to be reopened and restated; staff {t['b']['staff']}'s register address changed after the twelfth finding was written"
              + (f", and staff {t['e']['staff']}'s at the first close" if t.get("e") else "")
              + (f"; at the second close the actuals for {t['f']['duty']} moved (on-blocks {t['f']['on_blocks_before']} to {t['f']['on_blocks_after']}), adding a finding"
                 if t.get("f") else "")
              + (f"; discretion report {t['unsigned']['report_id']} for {t['unsigned']['duty']} was never signed, so that extension does not stand"
                 if t.get("unsigned") else "")
              + (f"; and after the twentieth finding was written the actuals for {t['c']['duty']} changed (on-blocks {t['c']['on_blocks_before']} to "
                 f"{t['c']['on_blocks_after']}), adding a finding." if t.get("c") else ".")]
    try:
        from generator import docs
        lines += ["", "Appendix A, Revision 13:", docs._table("Rev 13"), "Appendix A, Revision 14:", docs._table("Rev 14"),
                  f"Discretion allowance: Revision 13 two hours, Revision 14 ninety minutes. Revision 14 adds the extension to the following rest."]
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
    lines += ["", f"## Block close: status {run.close.get('Status')}, findings {run.close.get('Findings')}, excess total {run.close.get('Excess total min')}",
              "", f"## Notices sent ({len(run.sent)})"]
    for m in run.sent:
        lines += ["", f"### To {m.get('to_addr')}: {m.get('subject')}", str(m.get("body", ""))]
    open(out, "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    reference(sys.argv[2], sys.argv[3]) if sys.argv[1] == "reference" else state(sys.argv[2])
