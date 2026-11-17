"""Reference solution: run the September block audit end to end over the crew systems and the shared folder.

Like the reference oracles, every step is replayed on stdout as Claude Code stream-json (one tool_use and one
tool_result per MCP call, shell command or file read, then a result event carrying the final note); Harbor's oracle
agent saves it as /logs/agent/oracle.txt and tests/test.sh rebuilds the trajectory from it. The oracle reads the
records through the same tools an agent has, reads the decisive technical-log pages and duty-control call-log entries in the
shared folder and the discretion reports in the crew workspace, takes what each page and entry says from media_facts.json, derives the findings with derive.py, writes them in
the field guide's form, closes the block, re-reads and corrects after the close, notifies each pilot at the register's
current address and finishes CRW-2291.
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

DATA = Path(os.environ.get("CREW_DATA", "/workspace/data"))
PORT = {"LightNotion": 9099, "LightGmail": 9074, "LightJira": 9086, "LightGoogleDrive": 9078}
FINDINGS, CLOSE, CREW = "db-ftl-findings-sep-2026", "close-sep-2026", "db-crew-register"
ROSTER, ACT_NEW, ACT_OLD = "db-roster-aug-sep-2026", "db-duty-actuals-from-0915", "db-duty-actuals-to-0914"
REPORTS = "db-discretion-reports"
CORRECTIONS = "db-actuals-corrections"
COMPLIANCE = "ftl.compliance@fernhollow-air.example"
DECISIVE = {"voice": ("VN-119", "VN-717", "VN-686"), "techlog": ("TL-86765", "TL-28498"), "scans": ("CDR-1011",)}


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
    TRACE.step("Read", {"file_path": str(path)}, data.decode("utf-8", "replace")[:3000])
    return data.decode("utf-8", "replace") if path.suffix in (".md", ".csv", ".txt") else ""


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
    """The discretion reports as they stand now in the crew workspace, in the media form derive() reads."""
    return dict(media, scans=[{"id": r["Report number"], "duty": r["Duty ref"], "signed": r.get("Commander signed") == "Yes"} for r in rec["reports"]])


def finding_props(f):
    return {"Staff number": {"type": "rich_text", "value": f.staff}, "Duty ref": {"type": "rich_text", "value": f.key_ref},
            "Limit type": {"type": "select", "value": f.limit_type}, "Edition": {"type": "select", "value": f.edition},
            "Limit min": {"type": "number", "value": f.limit_min}, "Actual min": {"type": "number", "value": f.actual_min},
            "Excess min": {"type": "number", "value": f.excess_min}, "Evidence": {"type": "rich_text", "value": ", ".join(sorted(f.evidence))}}


MEANING = {"FDP": "your flight duty period ran longer than the chapter 7 maximum for its report time and sectors",
           "DISCRETION": "your flight duty period ran longer than the maximum plus the commander's discretion the revision allows",
           "REST": "the rest before this duty was shorter than the chapter 7 minimum",
           "DUTY_7D": "your duty in 7 consecutive days went over 60 hours", "DUTY_14D": "your duty in 14 consecutive days went over 110 hours",
           "DUTY_28D": "your duty in 28 consecutive days went over 190 hours"}


async def main() -> int:
    media = json.loads((HERE / "media_facts.json").read_text())
    manifest_files = {}
    for kind in ("voice", "techlog", "scans"):
        for e in media[kind]:
            manifest_files[e["id"]] = e
    notion, gmail, jira, drive = App("LightNotion"), App("LightGmail"), App("LightJira"), App("LightGoogleDrive")
    for app in (notion, gmail, jira, drive):
        await app.login()
    read_file(DATA / "ftl-audit-field-guide.md")
    for fid in ("file-oma7-rev13", "file-oma7-rev14"):
        await drive("download_file", file_id=fid)
    for tid in DECISIVE["voice"] + DECISIVE["techlog"]:
        read_file(DATA / manifest_files[tid]["file"])
    for sid in DECISIVE["scans"]:
        await notion("get_page", page_id=f"rpt-{sid}")
    rec = await records(notion, first=True)
    found = derive(rec, with_reports(media, rec))
    written = {}
    for f in found:
        r = await notion("create_page", parent_type="database", parent_id=FINDINGS, title=f"{f.staff} {f.key_ref} {f.limit_type}", properties=finding_props(f))
        written[f.key] = (r["output"]["id"], f, r["output"]["properties"]["Reference"]["value"])

    filed = set()

    async def file_corrections(rec):
        duty_of = {e["id"]: e["duty"] for kind in ("voice", "techlog") for e in media[kind] if e.get("duty")}
        duty_of.update({x["Report number"]: x["Duty ref"] for x in rec["reports"]})
        for _, f, _ in sorted(written.values(), key=lambda w: w[2]):
            for eid in sorted(f.evidence):
                if eid in filed:
                    continue
                duty = duty_of[eid]
                await notion("create_page", parent_type="database", parent_id=CORRECTIONS, title=f"{eid} {duty}",
                             properties={"Staff number": {"type": "rich_text", "value": f.staff}, "Duty ref": {"type": "rich_text", "value": duty},
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
        email = unwrap((await notion("get_page", page_id=f"crew-{staff}"))["output"])["Email"]
        lines = [f"{ref} {f.key_ref} {f.limit_type} excess {f.excess_min} min" for ref, f in sorted(items)]
        explain = [f"{ref}: {MEANING[f.limit_type]}, under chapter 7 {f.edition.replace('Rev', 'Revision')}." for ref, f in sorted(items)]
        body = ("The September 2026 flight and duty time audit recorded the following against your duties:\n\n" + "\n".join(lines) +
                "\n\nWhat each one means:\n" + "\n".join(explain) +
                "\n\nIf you have questions about these findings, contact crew compliance at " + COMPLIANCE + ".")
        await gmail("send_message", to_addr=email, subject=f"FTL audit September 2026: {staff}", body=body, from_addr=COMPLIANCE)
    fat = (await jira("search", jql="project = FAT AND status = Open", max_results=100))["output"]["issues"]
    for issue in sorted(fat, key=lambda i: i["key"]):
        staff = issue["fields"]["summary"].rsplit(" ", 1)[-1]
        if staff in by_staff:
            refs = ", ".join(sorted(ref for ref, _ in by_staff[staff]))
            desc = (issue["fields"]["description"] or "").rstrip() + "\nftl_findings: " + refs
            await jira("update_issue", issue_key=issue["key"], description=desc)
    editions = sorted({f.edition for f in found}, key=lambda e: int(e.split()[1]))
    issue = (await jira("get_issue", issue_key="CRW-2291"))["output"]
    desc = (issue.get("description") or "").rstrip() + "\n" + "\n".join(
        [f"findings: {len(found)}", f"excess_total_min: {total}", f"crew_notified: {len(by_staff)}", f"editions: {', '.join(editions)}"])
    await jira("update_issue", issue_key="CRW-2291", description=desc)
    trans = (await jira("get_transitions", issue_key="CRW-2291"))["output"]["transitions"]
    await jira("transition_issue", issue_key="CRW-2291", transition_id=next(t["id"] for t in trans if t["to"]["name"] == "Done"))
    TRACE.done(note(found, by_staff, total))
    return 0


RULE_TEXT = {"FDP": "the Appendix A maximum flight duty period read by the report time in base local time and the number of sectors (7.3)",
             "DISCRETION": "the Appendix A maximum plus the commander's discretion the revision allows, two hours under Revision 13 and ninety minutes under Revision 14 (7.4)",
             "REST": "the minimum rest of 7.5: the preceding duty period, not less than twelve hours at base or ten hours away, plus under Revision 14 any extension used on the preceding duty",
             "DUTY_7D": "60 hours in any 7 consecutive days (7.6)", "DUTY_14D": "110 hours in any 14 consecutive days (7.6)",
             "DUTY_28D": "190 hours in any 28 consecutive days (7.6)"}


def note(found, by_staff, total):
    L = ["September 2026 block audit, E190 captains and first officers based at Aberdeen.", "", "Findings:"]
    for f in sorted(found, key=lambda x: x.key):
        ev = f"; evidence {', '.join(sorted(f.evidence))}" if f.evidence else ""
        L.append(f"- Staff {f.staff}, {f.key_ref}, {f.limit_type}: limit {f.limit_min} min set by {RULE_TEXT[f.limit_type]}, under {f.edition}; "
                 f"actual {f.actual_min} min, excess {f.excess_min} min{ev}.")
    L += ["", "How the limits were set: each flight duty period limit is read from Appendix A by the report time in base local time and the number of sectors. "
          "A positioning leg before flying counts as a sector under Revision 14 and not under Revision 13. A discretion limit is the Appendix A maximum plus the "
          "revision's allowance, two hours under Revision 13 and ninety minutes under Revision 14, and an extension stands only when a commander's discretion "
          "report is filed and signed. Minimum rest is the preceding duty period, not less than twelve hours at base or ten hours away, and Revision 14 adds the "
          "length of a commander's extension to the rest that follows it. The cumulative limits are tested over rolling windows of consecutive days, not "
          "calendar weeks, with airport standby counting in full and home standby counting as one quarter.",
          "", "Which revision: a duty's revision is decided by its report time in base local time, UTC plus one hour in September 2026. Revision 13 applied "
          "to duties reporting before 00:00 base local time on 15 September 2026 and Revision 14 from then. I did not use the UTC date, which puts one duty "
          "reporting at 00:20 local on 15 September on the 14th, and I did not use the roster day printed on a roster line.",
          "", "Records I set aside: a technical-log page replaced a duty-actuals on-blocks time, and another technical-log page showed a sector "
          "(a diversion return) the duty-actuals record omitted; the technical log is the record of block times. A discretion report stood although the "
          "duty-actuals discretion flag said no, and an extension recorded in the duty actuals without a filed report was treated as no extension. A duty-control "
          "call-log entry moved a duty's start to a call-out from home standby with a taxi positioning leg. In two other call-log entries an airport announcement (a final "
          "call for a flight at gate three) showed that a standby the roster booked at home was served at the airport, so each counted in full. Last week's "
          "roster export was not used; the crew systems are the record. The branch representative's view was set aside because it carries no standing, "
          "and the draft side letter was set aside because it is unsigned and has no effect; nothing was mailed to the address they gave.",
          "", "What happened during the run: the archive of duty actuals refused queries, so its records were read one by one. The roster listing stopped "
          "short of the database's stated row count, so the missing rows were recovered by searching each pilot's staff number. A rate-limited query was "
          "retried. While the findings were being written the duty actuals changed for one duty, and after the first close they changed for another, so "
          "the block was reopened, the findings restated and the block closed again. After that second close a commander's discretion report that had "
          "stood unsigned was signed, so the extension stood, and the duty actuals moved another duty's on-blocks later: the block was reopened "
          "once more, the first duty's finding was restated from FDP to discretion in its own record, a finding was added for the second, and the "
          "block closed a third time. Another duty carried a discretion flag and a report in the duty actuals, but the commander had never signed "
          "that report, so the extension did not stand and it is an FDP finding. Two pilots' register addresses changed during the run, one while the findings were being written and one at the first close, and each notice went to the address the register held when it was sent.",
          "", "Corrections and follow-up: each technical-log page, discretion report and call-log entry that set a value in place of the duty actuals "
          "was filed in the duty-actuals corrections register before the close it supported, one record per identifier, and the duty actuals were "
          "left unchanged. After the notices, the open fatigue report of each notified pilot was annotated with the references of that pilot's findings.",
          "", f"Totals: {len(found)} findings, {total} minutes of excess in total, {len(by_staff)} pilots notified."]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
