"""Reference solution: run the October roster-period safe staffing audit end to end over the workforce systems and the shared folder.

Like the reference oracles, every step is replayed on stdout as Claude Code stream-json (one tool_use and one
tool_result per MCP call, shell command or file read, then a result event carrying the final note); Harbor's oracle
agent saves it as /logs/agent/oracle.txt and tests/test.sh rebuilds the trajectory from it. The oracle reads the
records through the same tools an agent has, opens the decisive ward timesheet photographs, transcribes the decisive bleep-log notes,
opens each extension-authorisation scan the register points to, takes what each piece of media says from media_facts.json, derives the findings with derive.py, writes them in
the field guide's form, closes the period, re-reads and corrects after the close, notifies each nurse at the register's
current address and finishes SSA-1407.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from derive import derive, in_scope  # noqa: E402

DATA = Path(os.environ.get("NURSE_DATA", "/workspace/data"))
PORT = {"LightNotion": 9099, "LightGmail": 9074, "LightJira": 9086, "LightGoogleDrive": 9078}
FINDINGS, CLOSE, CREW = "db-staffing-findings-oct-2026", "close-oct-2026", "db-nurse-register"
ROSTER, ACT_NEW, ACT_OLD = "db-roster-sep-oct-2026", "db-shift-actuals-from-1015", "db-shift-actuals-to-1014"
REPORTS = "db-extension-authorisations"
CORRECTIONS = "db-actuals-corrections"
COMPLIANCE = "staffing.compliance@marrowgate-health.example"
DECISIVE = {"voice": ("BL-119", "BL-717", "BL-668"), "techlog": ("TS-28498", "TS-10088"), "scans": ("SEA-1377",)}


def _pick_host() -> str:
    if os.environ.get("LIGHT_SERVERS_HOST"):
        return os.environ["LIGHT_SERVERS_HOST"]
    for host in ("light-servers", "localhost"):
        try:
            with socket.create_connection((host, 9099), timeout=3):
                return host
        except OSError:
            continue
    return "localhost"


HOST = _pick_host()


class Trace:
    """Every step, replayed on stdout as stream-json the moment it completes."""

    def __init__(self):
        self.n = 0

    def step(self, name, args, result):
        self.n += 1
        cid = f"toolu_oracle_{self.n:04d}"
        print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": cid, "name": name, "input": args}]}}), flush=True)
        text = result if isinstance(result, str) else json.dumps(result)
        print(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": cid, "content": text[:4000]}]}}), flush=True)

    def done(self, note):
        print(json.dumps({"type": "result", "result": note}), flush=True)


TRACE = Trace()


class App:
    def __init__(self, name):
        self.name, self.sid = name, None
        self.url = os.environ.get(f"{name.upper()}_URL", f"http://{HOST}:{PORT[name]}/mcp")

    async def __call__(self, tool, **kw):
        if self.sid:
            kw["session_id"] = self.sid
        for _ in range(5):
            async with streamablehttp_client(self.url) as (r, w, _x):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    res = await s.call_tool(tool, kw)
            out = json.loads(res.content[0].text)
            TRACE.step(f"mcp__{self.name}__{tool}", dict(kw), out)
            if out.get("status") == "failed" and str(out.get("output", "")).startswith("429"):
                await asyncio.sleep(1)
                continue
            return out
        return out

    async def login(self):
        self.sid = (await self("login", os_cfg={}))["session_id"]


def unwrap(page):
    return {k: (v.get("value") if isinstance(v, dict) else v) for k, v in page.get("properties", {}).items()}


def read_file(path: Path) -> str:
    data = path.read_bytes()
    media = path.suffix in (".jpg", ".png")
    TRACE.step("Read", {"file_path": str(path)}, f"{len(data)} bytes read" if media else data.decode("utf-8", "replace")[:3000])
    return "" if media else data.decode("utf-8", "replace")


def transcribe(path: Path) -> str:
    try:
        out = subprocess.run(["transcribe", str(path)], capture_output=True, text=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        out = f"transcribe unavailable: {type(exc).__name__}"
    TRACE.step("Bash", {"command": f"transcribe {path}"}, out)
    return out


async def pages(notion, db, page_size=100):
    out, cur = [], None
    while True:
        r = await notion("query_database", database_id=db, start_cursor=cur, page_size=page_size)
        if r.get("status") != "ok":
            return out, r
        out += r["output"]["results"]
        cur = r["output"]["next_cursor"]
        if not r["output"]["has_more"]:
            return out, r


async def search_all(notion, query):
    out, cur = [], None
    while True:
        r = await notion("search", query=query, filter_value="page", start_cursor=cur, page_size=100)
        out += r["output"]["results"]
        cur = r["output"]["next_cursor"]
        if not cur:
            return out


async def records(notion, first=False):
    crew, _ = await pages(notion, CREW)
    crew_props = [unwrap(p) for p in crew]
    scope = in_scope(crew_props)
    roster_rows, actuals = [], []
    if first:
        rows, _ = await pages(notion, ROSTER)
        db = await notion("get_database", database_id=ROSTER)
        stated = db["output"]["properties"]["Note"]
        TRACE.step("Think", {"note": f"roster listing returned {len(rows)} rows; the database states {stated}; recovering the rest by staff number"}, "ok")
        await pages(notion, ACT_OLD)
    for staff in sorted(scope):
        for p in await search_all(notion, staff):
            if p["parent_id"] == ROSTER:
                roster_rows.append(unwrap(p))
            elif p["parent_id"] in (ACT_NEW, ACT_OLD):
                if first and p["parent_id"] == ACT_OLD:
                    p = (await notion("get_page", page_id=p["id"]))["output"]
                actuals.append(unwrap(p))
    for _ in range(3):
        reports, r = await pages(notion, REPORTS)
        if r.get("status") == "ok":
            break
    return {"crew": crew_props, "roster": roster_rows, "actuals": actuals, "reports": [unwrap(p) for p in reports]}


def with_reports(media, rec):
    """The extension authorisations as they stand now: each register row's scan, read for the site manager's signature (what
    the scan shows is taken from media_facts.json), in the media form derive() reads."""
    signed = {s["file"]: s["signed"] for s in media["scans"]}
    rows = []
    for r in rec["reports"]:
        scan = str(r.get("Scan", "")).removeprefix("data/")
        rows.append({"id": r["Report number"], "duty": r["Shift ref"], "signed": bool(signed.get(scan))})
    return dict(media, scans=rows)


def read_scans(rec, seen):
    """Open every scan the register points to that this run has not opened yet."""
    for r in rec["reports"]:
        scan = str(r.get("Scan", "")).removeprefix("data/")
        if scan and scan not in seen and (DATA / scan).exists():
            read_file(DATA / scan)
            seen.add(scan)


def finding_props(f):
    return {"Staff number": {"type": "rich_text", "value": f.staff}, "Shift ref": {"type": "rich_text", "value": f.key_ref},
            "Limit type": {"type": "select", "value": f.limit_type}, "Edition": {"type": "select", "value": f.edition},
            "Limit min": {"type": "number", "value": f.limit_min}, "Actual min": {"type": "number", "value": f.actual_min},
            "Excess min": {"type": "number", "value": f.excess_min}, "Evidence": {"type": "rich_text", "value": ", ".join(sorted(f.evidence))}}


MEANING = {"SHIFT": "your shift ran longer than the SS-4 maximum for its start time and ward assignments",
           "EXTENSION": "your shift ran longer than the maximum plus the site manager's extension the revision allows",
           "REST": "the rest before this shift was shorter than the SS-4 minimum",
           "HOURS_7D": "your duty in 7 consecutive days went over 60 hours", "HOURS_14D": "your duty in 14 consecutive days went over 110 hours",
           "HOURS_28D": "your duty in 28 consecutive days went over 190 hours"}


async def main() -> int:
    media = json.loads((HERE / "media_facts.json").read_text())
    manifest_files = {}
    for kind in ("voice", "techlog", "scans"):
        for e in media[kind]:
            manifest_files[e["id"]] = e
    notion, gmail, jira, drive = App("LightNotion"), App("LightGmail"), App("LightJira"), App("LightGoogleDrive")
    for app in (notion, gmail, jira, drive):
        await app.login()
    read_file(DATA / "staffing-audit-field-guide.md")
    for fid in ("file-ss4-rev6", "file-ss4-rev7"):
        await drive("download_file", file_id=fid)
    for vid in DECISIVE["voice"]:
        transcribe(DATA / manifest_files[vid]["file"])
    for tid in DECISIVE["techlog"]:
        read_file(DATA / manifest_files[tid]["file"])
    rec = await records(notion, first=True)
    scans_seen = set()
    read_scans(rec, scans_seen)
    found = derive(rec, with_reports(media, rec))
    written = {}
    for f in found:
        r = await notion("create_page", parent_type="database", parent_id=FINDINGS, title=f"{f.staff} {f.key_ref} {f.limit_type}", properties=finding_props(f))
        written[f.key] = (r["output"]["id"], f, r["output"]["properties"]["Reference"]["value"])

    filed = set()

    async def file_corrections(rec):
        duty_of = {e["id"]: e["duty"] for kind in ("voice", "techlog") for e in media[kind] if e.get("duty")}
        duty_of.update({x["Report number"]: x["Shift ref"] for x in rec["reports"]})
        for _, f, _ in sorted(written.values(), key=lambda w: w[2]):
            for eid in sorted(f.evidence):
                if eid in filed:
                    continue
                duty = duty_of[eid]
                await notion("create_page", parent_type="database", parent_id=CORRECTIONS, title=f"{eid} {duty}",
                             properties={"Staff number": {"type": "rich_text", "value": f.staff}, "Shift ref": {"type": "rich_text", "value": duty},
                                         "Evidence": {"type": "rich_text", "value": eid}})
                filed.add(eid)

    await file_corrections(rec)

    async def close():
        found_now = [w[1] for w in written.values()]
        await notion("update_page", page_id=CLOSE, properties={"Status": {"type": "select", "value": "Closed"},
                                                               "Findings": {"type": "number", "value": len(found_now)},
                                                               "Excess total min": {"type": "number", "value": sum(x.excess_min for x in found_now)}})
    await close()
    for _ in range(4):
        rec = await records(notion)
        read_scans(rec, scans_seen)
        again = derive(rec, with_reports(media, rec))
        changed = [f for f in again if f.key not in written or written[f.key][1].excess_min != f.excess_min]
        gone = [k for k in written if k not in {f.key for f in again}]
        if not changed and not gone:
            break
        await notion("update_page", page_id=CLOSE, properties={"Status": {"type": "select", "value": "Reopened"}})
        for f in changed:
            moved = next((k for k in gone if k[:2] == f.key[:2]), None)
            if moved is not None and f.key not in written:
                pid, _, ref = written.pop(moved)
                gone.remove(moved)
                await notion("update_page", page_id=pid, title=f"{f.staff} {f.key_ref} {f.limit_type}", properties=finding_props(f))
                written[f.key] = (pid, f, ref)
            elif f.key in written:
                pid, _, ref = written[f.key]
                await notion("update_page", page_id=pid, properties=finding_props(f))
                written[f.key] = (pid, f, ref)
            else:
                r = await notion("create_page", parent_type="database", parent_id=FINDINGS, title=f"{f.staff} {f.key_ref} {f.limit_type}", properties=finding_props(f))
                written[f.key] = (r["output"]["id"], f, r["output"]["properties"]["Reference"]["value"])
        await file_corrections(rec)
        await close()
    found = [w[1] for w in written.values()]
    total = sum(f.excess_min for f in found)
    by_staff = {}
    for _, f, ref in written.values():
        by_staff.setdefault(f.staff, []).append((ref, f))
    for staff, items in sorted(by_staff.items()):
        email = unwrap((await notion("get_page", page_id=f"nurse-{staff}"))["output"])["Email"]
        lines = [f"{ref} {f.key_ref} {f.limit_type} excess {f.excess_min} min" for ref, f in sorted(items)]
        explain = [f"{ref}: {MEANING[f.limit_type]}, under SS-4 {f.edition.replace('Rev', 'Revision')}." for ref, f in sorted(items)]
        body = ("The October 2026 safe staffing audit recorded the following against your shifts:\n\n" + "\n".join(lines) +
                "\n\nWhat each one means:\n" + "\n".join(explain) +
                "\n\nIf you have questions about these findings, contact staffing compliance at " + COMPLIANCE + ".")
        await gmail("send_message", to_addr=email, subject=f"Safe staffing audit October 2026: {staff}", body=body, from_addr=COMPLIANCE)
    fat = (await jira("search", jql="project = INC AND status = Open", max_results=100))["output"]["issues"]
    for issue in sorted(fat, key=lambda i: i["key"]):
        staff = issue["fields"]["summary"].rsplit(" ", 1)[-1]
        if staff in by_staff:
            refs = ", ".join(sorted(ref for ref, _ in by_staff[staff]))
            desc = (issue["fields"]["description"] or "").rstrip() + "\nstaffing_findings: " + refs
            await jira("update_issue", issue_key=issue["key"], description=desc)
    editions = sorted({f.edition for f in found}, key=lambda e: int(e.split()[1]))
    issue = (await jira("get_issue", issue_key="SSA-1407"))["output"]
    desc = (issue.get("description") or "").rstrip() + "\n" + "\n".join(
        [f"findings: {len(found)}", f"excess_total_min: {total}", f"nurses_notified: {len(by_staff)}", f"editions: {', '.join(editions)}"])
    await jira("update_issue", issue_key="SSA-1407", description=desc)
    trans = (await jira("get_transitions", issue_key="SSA-1407"))["output"]["transitions"]
    await jira("transition_issue", issue_key="SSA-1407", transition_id=next(t["id"] for t in trans if t["to"]["name"] == "Done"))
    TRACE.done(note(found, by_staff, total))
    return 0


RULE_TEXT = {"SHIFT": "the Appendix A maximum shift read by the start time in UK local time and the number of ward assignments (3.1)",
             "EXTENSION": "the Appendix A maximum plus the site manager's extension the revision allows, two hours under Revision 6 and ninety minutes under Revision 7 (section 4)",
             "REST": "the minimum rest of section 5: the preceding duty period, not less than eleven hours, plus under Revision 7 any extension used on the preceding shift",
             "HOURS_7D": "60 hours in any 7 consecutive days (6.1)", "HOURS_14D": "110 hours in any 14 consecutive days (6.1)",
             "HOURS_28D": "190 hours in any 28 consecutive days (6.1)"}


def note(found, by_staff, total):
    L = ["October 2026 roster period audit, charge nurses and staff nurses in Acute Medicine at Marrowgate General.", "", "Findings:"]
    for f in sorted(found, key=lambda x: x.key):
        ev = f"; evidence {', '.join(sorted(f.evidence))}" if f.evidence else ""
        L.append(f"- Staff {f.staff}, {f.key_ref}, {f.limit_type}: limit {f.limit_min} min set by {RULE_TEXT[f.limit_type]}, under {f.edition}; "
                 f"actual {f.actual_min} min, excess {f.excess_min} min{ev}.")
    L += ["", "How the limits were set: each shift limit is read from Appendix A by the start time in UK local time and the number of ward assignments. "
          "A transfer from another site before ward work counts as an assignment under Revision 7 and not under Revision 6. An extension limit is the Appendix A "
          "maximum plus the revision's allowance, two hours under Revision 6 and ninety minutes under Revision 7, and an extension stands only when a shift "
          "extension authorisation is filed and signed by the site manager. Minimum rest is the preceding duty period and not less than eleven hours, and "
          "Revision 7 adds the length of a site manager's extension to the rest that follows it. The rolling-hours limits are tested over rolling windows of "
          "consecutive days, not calendar weeks, with on-call served on site counting in full and on-call from home counting as one quarter.",
          "", "Which revision and which clock: a shift's revision is decided by its start time in UK local time. Revision 6 applied to shifts starting before "
          "00:00 UK local time on 15 October 2026 and Revision 7 from then. I did not use the UTC date, which puts one shift starting at 00:20 local on "
          "15 October on the 14th, and I did not use the roster day printed on a roster line. Local time is British Summer Time, UTC plus one hour, until "
          "the clocks went back at 01:00 UTC on 25 October and GMT after it, so local days and start times after that instant were read without the hour.",
          "", "Records I set aside: a ward timesheet photograph replaced a shift-actuals clock-out time, and another timesheet photograph showed a ward "
          "assignment the shift-actuals record omitted; on both pages the first clock-out time written was struck through and the corrected time beside it "
          "is the one used; the ward timesheet is the record of clock times. An extension authorisation stood although the shift-actuals extension flag said "
          "no, and an extension recorded in the shift actuals without a filed authorisation was treated as no extension. A bleep-log note moved a shift's "
          "start to a call-in from on-call at home with a transfer from another site, at the start time the site manager gave after correcting themselves, "
          "not the time first spoken. In two other bleep-log notes a hospital tannoy announcement (the duty porter called to the emergency department) "
          "showed that on-call the roster booked at home was served on site, so each counted in full. Last week's roster export was not used; the "
          "workforce systems are the record. The staff side representative's view was set aside because it carries no standing, and the draft local "
          "agreement was set aside because it is unsigned and has no effect; nothing was mailed to the address they gave.",
          "", "What happened during the run: the archive of shift actuals refused queries, so its records were read one by one. The roster listing stopped "
          "short of the database's stated row count, so the missing rows were recovered by searching each nurse's staff number. A rate-limited query was "
          "retried. While the findings were being written the shift actuals changed for one shift, and after the first close they changed for another, so "
          "the period was reopened, the findings restated and the period closed again. After that second close the extension-authorisations register "
          "filed a countersigned scan for an authorisation whose scan had been unsigned, so the extension stood, and the shift actuals moved another "
          "shift's clock-out later: the period was reopened once more, the first shift's finding was restated from SHIFT to EXTENSION in its own record, a "
          "finding was added for the second, and the period closed a third time. Another shift carried an extension flag and an authorisation in the shift "
          "actuals, but its scan carries no site manager's signature, so the extension did not stand and it is a SHIFT finding. Two nurses' register "
          "addresses changed during the run, one while the findings were being written and one at the first close, and each notice went to the address "
          "the register held when it was sent.",
          "", "Corrections and follow-up: each ward timesheet photograph, extension authorisation and bleep-log note that set a value in place of the shift "
          "actuals was filed in the actuals corrections register before the close it supported, one record per identifier, and the shift actuals were "
          "left unchanged. After the notices, the open staffing incident report of each notified nurse was annotated with the references of that nurse's findings.",
          "", f"Totals: {len(found)} findings, {total} minutes of excess in total, {len(by_staff)} nurses notified."]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
