"""Reference solution: work trace TR-2026-031 end to end over the plant systems.

Every step is replayed on stdout as Claude Code stream-json; Harbor's oracle agent saves it as /logs/agent/oracle.txt and
tests/test.sh rebuilds the trajectory from it. The oracle reads the quality library and every register through the same
tools an agent has (the ticket listing by status, since the unfiltered listing truncates; the write-offs by search,
since listing them is refused), derives the AL-3 trace with derive.py, quarantines and holds, re-reads after the holds
until a pass changes nothing (releasing what the plant's changes cleared), marks shipped pallets for recall, sends one
recall request per customer, completes the trace report and writes the closing note.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from derive import LOT, SHIFT_LEADS, SUPPLIER, derive, minutes  # noqa: E402
from tracerules import ON_SITE, VALIDATING_TESTS  # noqa: E402

DATA = Path(os.environ.get("LT_DATA", "/workspace/data"))
PORT = {"LightNotion": 9099, "LightGmail": 9074, "LightGoogleDrive": 9078}
MAILBOX = "technical@kestrelfold-foods.example"
NOTICE, REPORT = "TR-2026-031", "tr-2026-031"
DB = {"receipts": "db-goods-receipts", "tubs": "db-stores-tubs", "runs": "db-production-runs", "tickets": "db-scale-tickets",
      "cleandowns": "db-line-cleandowns", "writeoffs": "db-write-offs", "pallets": "db-pallet-stock", "customers": "db-customers",
      "lab": "db-lab-results", "recipes": "db-blend-recipes"}


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
            text = res.content[0].text if res.content else ""
            try:
                out = json.loads(text)
            except ValueError:
                out = {"status": "failed" if res.isError else "ok", "output": text}
            TRACE.step(f"mcp__{self.name}__{tool}", dict(kw), out)
            if out.get("status") == "failed" and str(out.get("output", "")).startswith("Error 429"):
                await asyncio.sleep(1)
                continue
            return out
        return out

    async def login(self):
        self.sid = (await self("login", os_cfg={}))["session_id"]


def unwrap(page):
    return {**{k: (v.get("value") if isinstance(v, dict) else v) for k, v in page.get("properties", {}).items()}, "_id": page["id"]}


async def pages(notion, db, status=None):
    out, cur = [], None
    while True:
        kw = {"database_id": db, "start_cursor": cur, "page_size": 100}
        if status:
            kw["filter_status"] = status
        r = await notion("query_database", **kw)
        if r.get("status") != "ok":
            return None
        out += [unwrap(p) for p in r["output"]["results"]]
        cur = r["output"]["next_cursor"]
        if not r["output"]["has_more"]:
            return out


async def search_all(notion, query):
    out, cur = [], None
    while True:
        r = await notion("search", query=query, filter_value="page", start_cursor=cur, page_size=100)
        out += r["output"]["results"]
        cur = r["output"]["next_cursor"]
        if not r["output"]["has_more"]:
            return out


async def read_all(notion) -> dict:
    rec = {}
    for key in ("receipts", "tubs", "runs", "cleandowns", "pallets", "customers", "lab", "recipes"):
        rows = None
        while rows is None:
            rows = await pages(notion, DB[key])
        rec[key] = rows
    # the unfiltered ticket listing stops short of its stated row count; read it by status instead
    rec["tickets"] = []
    for st in ("Posted", "Unposted"):
        rows = None
        while rows is None:
            rows = await pages(notion, DB["tickets"], st)
        rec["tickets"] += rows
    # shift-lead corrections live in comments on the ticket pages; who wrote each comment is in the workspace users
    rec["comments"] = (await notion("list_comments"))["output"]["results"]
    users = await notion("list_users")
    rec["users"] = (users.get("output") or {}).get("results", []) if users.get("status") == "ok" else []
    # listing the write-off register is refused; open every write-off record found by search
    rec["writeoffs"] = []
    for p in await search_all(notion, "Write-off"):
        if p["parent_id"] == DB["writeoffs"]:
            rec["writeoffs"].append(unwrap((await notion("get_page", page_id=p["id"]))["output"]))
    return rec


def cap(s):
    return s[:1].upper() + s[1:]


def swab_clause(node, gap):
    """Why the clean-downs around a carry-over edge left the line unvalidated for sesame, from the trace's own gap record."""
    g = (gap or {}).get(node)
    if g is None:
        return ", "
    bits = []
    for c, late in g["near"]:
        if late:
            bits.append(f"the {c.test} clean-down swabbed as {c.id} was logged as finishing at {c.when}, after {node} had already started, "
                        f"so it did not lie between the runs (SOP-CD-2 5)")
        elif c.swab == "Pass":
            bits.append(f"swab {c.id} at {c.when} returned Pass but on a {c.test} test, which covers that allergen alone and does not "
                        f"validate the line for sesame (SOP-CD-2 4)")
        elif c.swab == "Pending":
            bits.append(f"swab {c.id} at {c.when} was still Pending, and a Pending result does not validate a clean-down (SOP-CD-2 3)")
        else:
            bits.append(f"swab {c.id} at {c.when} returned {c.swab}, so that clean-down did not validate the line (SOP-CD-2 3)")
    return " — " + "; ".join(bits or ["no clean-down was swabbed between them at all"]) + " — "


def route(node, why, gap=None, depth=0):
    w = why.get(node)
    if w is None or depth > 40:
        return node
    if w == "receipt":
        return f"{node} (receipt of {LOT})"
    kind, src = w.split(":", 1)
    if kind == "carry":
        return f"{node} followed on the same line, with no Pass swab between{swab_clause(node, gap)}run {route(src, why, gap, depth + 1)}"
    word = {"usage": "took", "receipt": "filled from", "decant": "decanted from",
            "presumed": "is presumed under AL-3 4.3 to have taken from short tub"}[kind]
    return f"{node} {word} {route(src, why, gap, depth + 1)}"


async def main() -> int:
    notion, gmail, drive = App("LightNotion"), App("LightGmail"), App("LightGoogleDrive")
    for app in (notion, gmail, drive):
        await app.login()
    for fid in ("file-al3", "file-sop-cd2", "file-sop-st5", "file-rp4"):
        await drive("download_file", file_id=fid)
    await gmail("list_messages", max_results=50)
    readme = (DATA / "README.md").read_text() if (DATA / "README.md").exists() else ""
    TRACE.step("Read", {"file_path": str(DATA / "README.md")}, readme[:2000] or "missing")

    first = await read_all(notion)
    d = derive(first)
    status = {p["Pallet"]: ("Available", p["_id"]) for p in first["pallets"]}
    tub_page = {t["Tub"]: t["_id"] for t in first["tubs"]}
    for tub in d["quarantine"]:
        await notion("update_page", page_id=tub_page[tub], properties={"Status": {"type": "select", "value": "Quarantined"}})
    rec = first
    for _ in range(6):
        changed = False
        for pal in d["held"]:
            if status[pal][0] != "Held":
                await notion("update_page", page_id=status[pal][1], properties={"Status": {"type": "select", "value": "Held"}})
                status[pal] = ("Held", status[pal][1])
                changed = True
        leaving = {x for v in d["recall"].values() for x in v}
        for pal, (st, pid) in list(status.items()):
            if st == "Held" and pal not in d["held"] and pal not in leaving:
                await notion("update_page", page_id=pid, properties={"Status": {"type": "select", "value": "Released"}})
                status[pal] = ("Released", pid)
                changed = True
        rec = await read_all(notion)
        d2 = derive(rec)
        for pal, (st, pid) in list(status.items()):
            if st == "Held" and pal in {x for v in d2["recall"].values() for x in v}:
                await notion("update_page", page_id=pid, properties={"Status": {"type": "select", "value": "Recall requested"}})
                status[pal] = ("Recall requested", pid)
                changed = True
        if not changed and d2["held"] == d["held"] and d2["recall"] == d["recall"] and d2["quarantine"] == d["quarantine"]:
            break
        for tub in sorted(set(d2["quarantine"]) - set(d["quarantine"])):
            await notion("update_page", page_id=tub_page[tub], properties={"Status": {"type": "select", "value": "Quarantined"}})
        d = d2
    for cust, pals in sorted(d["recall"].items()):
        for pal in pals:
            await notion("update_page", page_id=status[pal][1], properties={"Status": {"type": "select", "value": "Recall requested"}})
            status[pal] = ("Recall requested", status[pal][1])
    contact = {c["Customer"]: c["Recall contact"] for c in rec["customers"]}
    for cust, pals in sorted(d["recall"].items()):
        body = "\n".join([f"Kestrel Fold Foods is recalling the following pallets you received under trace {NOTICE}: smoked paprika lot "
                          f"{LOT} supplied to us contained undeclared sesame. Please quarantine them and confirm.", ""]
                         + [f"{p} {' '.join(bs)}" for p, bs in sorted(pals.items())])
        await gmail("send_message", to_addr=contact[cust], subject=f"Recall request {NOTICE} {cust}", body=body, from_addr=MAILBOX)
    mb = d["mass_balance"]
    await notion("update_page", page_id=REPORT, properties={
        "Batches implicated": {"type": "number", "value": len(d["batches"])},
        "Batch list": {"type": "rich_text", "value": ", ".join(sorted(d["batches"]))},
        "Pallets held": {"type": "number", "value": len(d["held"])},
        "Pallets recalled": {"type": "number", "value": sum(map(len, d["recall"].values()))},
        "Received kg": {"type": "number", "value": mb["received"]}, "Used kg": {"type": "number", "value": mb["used"]},
        "On hand kg": {"type": "number", "value": mb["on_hand"]}, "Written off kg": {"type": "number", "value": mb["waste"]},
        "Unaccounted kg": {"type": "number", "value": mb["unaccounted"]}})
    await notion("update_page", page_id=REPORT, properties={"Status": {"type": "select", "value": "Complete"}})
    # RP-4 6: the laboratory reviews its results on completion; read again, and reopen if anything moved
    mid = d
    rec = await read_all(notion)
    d = derive(rec)
    reopened, added = [], {}
    if (d["held"], d["recall"], d["quarantine"], d["mass_balance"]) != (mid["held"], mid["recall"], mid["quarantine"], mid["mass_balance"]):
        await notion("update_page", page_id=REPORT, properties={"Status": {"type": "select", "value": "Open"}})
        for pal in d["held"]:
            if status[pal][0] != "Held":
                await notion("update_page", page_id=status[pal][1], properties={"Status": {"type": "select", "value": "Held"}})
                status[pal] = ("Held", status[pal][1])
        for cust, pals in sorted(d["recall"].items()):
            new = {p: bs for p, bs in pals.items() if p not in mid["recall"].get(cust, {})}
            for pal in new:
                await notion("update_page", page_id=status[pal][1], properties={"Status": {"type": "select", "value": "Recall requested"}})
                status[pal] = ("Recall requested", status[pal][1])
            if new:
                added[cust] = dict(new)
                body = "\n".join([f"Further to our recall request under trace {NOTICE}, please also quarantine these pallets:", ""]
                                 + [f"{p} {' '.join(bs)}" for p, bs in sorted(new.items())])
                await gmail("send_message", to_addr=contact[cust], subject=f"Recall request {NOTICE} {cust} (additional)", body=body, from_addr=MAILBOX)
        reopened = sorted(set(d["batches"]) - set(mid["batches"]))
        mb = d["mass_balance"]
        await notion("update_page", page_id=REPORT, properties={
            "Batches implicated": {"type": "number", "value": len(d["batches"])},
            "Batch list": {"type": "rich_text", "value": ", ".join(sorted(d["batches"]))},
            "Pallets held": {"type": "number", "value": len(d["held"])},
            "Pallets recalled": {"type": "number", "value": sum(map(len, d["recall"].values()))},
            "Received kg": {"type": "number", "value": mb["received"]}, "Used kg": {"type": "number", "value": mb["used"]},
            "On hand kg": {"type": "number", "value": mb["on_hand"]}, "Written off kg": {"type": "number", "value": mb["waste"]},
            "Unaccounted kg": {"type": "number", "value": mb["unaccounted"]}})
        await notion("update_page", page_id=REPORT, properties={"Status": {"type": "select", "value": "Complete"}})
    TRACE.done(note(first, rec, derive(first), d, status, reopened, added))
    return 0


def note(first, rec, d0, d, status, reopened=(), added=None):
    why, gap, imp = d["trace"].why, d["trace"].gap, d["trace"].implicated
    L = [f"Trace {NOTICE}: {SUPPLIER} smoked paprika lot {LOT}, undeclared sesame. Complete.", "",
         f"Implicated finished batches ({len(d['batches'])}), each with the route by which the lot reached it:"]
    L += [f"- {route(b, why, gap)}" for b in d["batches"]]
    L += ["", f"Tubs quarantined: {', '.join(d['quarantine'])}.",
          f"Pallets held on site: {len(d['held'])}. Pallets marked Recall requested: {sum(map(len, d['recall'].values()))}, in one recall request per customer: "
          + "; ".join(f"{c} {len(p)}" for c, p in sorted(d["recall"].items())) + "."]
    released = sorted(p for p, (st, _) in status.items() if st == "Released")
    tk0 = {t["Ticket no"]: t["Status"] for t in first["tickets"]}
    posted = [t for t in rec["tickets"] if t["Status"] == "Posted" and tk0.get(t["Ticket no"]) == "Unposted"]
    cd0 = {c["_id"]: c["Result"] for c in first["cleandowns"]}
    swabs = [c for c in rec["cleandowns"] if cd0.get(c["_id"]) != c["Result"]]
    loc0 = {p["Pallet"]: p["Location"] for p in first["pallets"]}
    moved = [p for p in rec["pallets"] if loc0.get(p["Pallet"]) != p["Location"]]
    L += ["", "What changed while I worked:"]
    pres = {k: v.split(":", 1)[1] for k, v in why.items() if v.startswith("presumed:")}
    for blend, tub in sorted(pres.items()):
        L.append(f"- AL-3 4.3: tub {tub} reconciles more than 2 kg short (net stores count, after the bin's tare), so blend {blend}, made between "
                 f"its first and last posted draw with a recipe using smoked paprika, is presumed to have taken from it; the window opened only "
                 f"once the late ticket was posted.")
    if reopened:
        L.append(f"- After I completed the report, the laboratory revised a swab from Pass to Fail; I set the report back to Open, traced the new "
                 f"carry-over to {', '.join(reopened)}, held or recalled its pallets (sending additional recall requests where needed), and completed it again.")
    if reopened:
        L.append("- On reopening I sent an additional recall request only to a customer whose pallet list had actually grown, and that request listed "
                 "only the pallets newly added to that customer's list, never the pallets already recalled from them; a customer whose list was "
                 "unchanged was not written to a second time. "
                 + ("Lists that grew: " + "; ".join(f"{c} {', '.join(sorted(p))}" for c, p in sorted(added.items())) + "."
                    if added else f"On this trace no customer's list grew — every pallet of {', '.join(reopened)} was still on site and was held, "
                                  "not recalled — so no additional recall request was sent to anyone."))
    for t in posted:
        L.append(f"- Scale ticket {t['Ticket no']} was posted: {t['Quantity']} {t['Unit']} from {t['Source']} into {t['Run']}, which brought "
                 f"{t['Run']} into the trace and reduced the unaccounted figure from {d0['mass_balance']['unaccounted']} kg to {d['mass_balance']['unaccounted']} kg.")
    for c in swabs:
        at = minutes(c["Finished"])
        on_line = sorted((r for r in d["runs"].values() if r.line == c["Line"]), key=lambda r: (r.start, r.id))
        prev = max((r for r in on_line if r.end <= at), key=lambda r: (r.end, r.id), default=None)
        nxt = min((r for r in on_line if r.start >= at), key=lambda r: (r.start, r.id), default=None)
        between = (f", the clean-down between {prev.id} and {nxt.id}," if prev and nxt else "")
        if c["Result"] == "Pass":
            gone = sorted(set(d0["trace"].implicated) - imp)
            gone_b = sorted(set(d0["batches"]) - set(d["batches"]))
            carried = f"{nxt.id} no longer followed {prev.id} with no Pass swab between, so {nxt.id}" if prev and nxt else "the chain behind it"
            L.append(f"- Swab {c['Swab']} on {c['Line']}{between} was revised from {cd0.get(c['_id'])} to Pass, so the line was validated clean there: "
                     f"{carried} left the trace, and the finished batches that left with it are {', '.join(gone_b)} "
                     f"(everything that dropped out: {', '.join(gone)}). Pallets I had held on those batches were set to Released: {', '.join(released)}.")
        else:
            ran_on = f"the carry-over from {prev.id} ran on into {nxt.id}" if prev and nxt else "the carry-over behind it continued"
            L.append(f"- Swab {c['Swab']} on {c['Line']}{between} was revised from {cd0.get(c['_id'])} to {c['Result']}, so that clean-down did not "
                     f"validate the line after all (SOP-CD-2 3: only a Pass validates) and {ran_on}"
                     + (f", bringing {', '.join(reopened)} into the trace." if reopened else "."))
    for p in moved:
        was = next(x for x in first["pallets"] if x["Pallet"] == p["Pallet"])
        if p["Location"] == "In transit":
            L.append(f"- Pallet {p['Pallet']} ({p['Batch']}), which I had held in the {was['Location']}, was sent out in transit to {p['Customer']}; "
                     f"it was changed from Held to Recall requested and included in that customer's recall request.")
        else:
            L.append(f"- Pallet {p['Pallet']} ({p['Batch']}), booked as shipped to {was['Customer']}, was found in the {p['Location']}; "
                     f"it was held, not recalled, and left out of that customer's recall request.")
    twin = sorted({r["Supplier"] for r in rec["receipts"] if r["Supplier lot"] == LOT and r["Supplier"] != SUPPLIER})
    tkt = {t["_id"]: t for t in rec["tickets"]}
    corr = []
    for pid, src in sorted(d["fix"].items()):
        t = tkt.get(pid, {})
        no, run, was = t.get("Ticket no", pid.removeprefix("tkt-")), t.get("Run", ""), t.get("Source", "")
        if src in imp and was not in imp:
            corr.append(f"ticket {no}, the draw into {run}, was corrected from source {was} to {src}, and since {src} holds the lot while {was} does "
                        f"not, that correction is what brings {run} into the trace: {route(run, why, gap)}")
        elif was in imp and src not in imp:
            corr.append(f"ticket {no}, the draw into {run}, was corrected from the suspect tub {was} to the clean tub {src}, so nothing of the lot "
                        f"went into {run} on that draw and {run} is not implicated; {was} itself stays suspect and quarantined, and the batches that "
                        f"did draw on {was} stay in the trace")
        else:
            corr.append(f"ticket {no}, the draw into {run}, was corrected from source {was} to {src}")
    names = {u["id"]: u.get("name", "") for u in rec.get("users", [])}
    op = [tkt[c["parent_page_id"]] for c in rec.get("comments", [])
          if names.get(c.get("author_id"), "") not in SHIFT_LEADS and "TUB-" in (c.get("text") or "") and c.get("parent_page_id") in tkt]
    op_txt = ("".join(f" A comment by an operator on ticket {t['Ticket no']}, the draw into {t['Run']}, claiming a different source was set aside "
                      f"because an operator cannot correct a ticket, so {t['Run']} was traced on the source the ticket records." for t in op)
              or " A comment by an operator claiming a different source was set aside because an operator cannot correct a ticket.")
    exc = sorted(d["trace"].excluded.items(), key=lambda kv: (kv[1]["swab"].test != "Sesame", kv[0]))
    exc_txt = "; ".join(f"{run} is not implicated by carry-over from {e['prev']} because swab {e['swab'].id} passed on a {e['swab'].test} test at "
                        f"{e['swab'].when}, between the two runs, which validated the line" for run, e in exc[:4])
    wrong_test, late_cd = [], []
    for run, g in sorted(gap.items()):
        for c, late in g["near"]:
            if late:
                late_cd.append(f"the {c.test} clean-down {c.id} between {g['prev']} and {run} was logged as finishing at {c.when}, after {run} had "
                               f"already started, so it did not lie between the two runs and {run} is reached by carry-over from {g['prev']} all the same")
            elif c.swab == "Pass" and c.test not in VALIDATING_TESTS:
                tail = (f"so {run} is implicated by carry-over from {g['prev']} even though a swab between them passed"
                        if run in imp else
                        f"so that swab did not break the line between {g['prev']} and {run}; {run} is out of the trace only because the chain into "
                        f"{g['prev']} had already been broken upstream"
                        + (f" by the validating Pass {gap[g['prev']]['pass'][0].id} after {gap[g['prev']]['prev']}"
                           if gap.get(g["prev"], {}).get("pass") else ""))
                wrong_test.append(f"swab {c.id}, the clean-down between {g['prev']} and {run}, returned Pass on a {c.test} test at {c.when}, which "
                                  f"covers that allergen alone and does not validate the line for sesame, {tail}")
    mix = next((p for p in rec["pallets"] if len(p["Batch"].split(",")) > 1
                and [b.strip() for b in p["Batch"].split(",")][0] not in set(d["batches"])
                and [b.strip() for b in p["Batch"].split(",")][1] in set(d["batches"])), None)
    mix_txt = ""
    if mix:
        b0, b1 = [b.strip() for b in mix["Batch"].split(",")][:2]
        mix_txt = (f" {mix['Pallet']} is one such pallet: it carries {b0} and {b1}, and only the second, {b1}, is implicated, so the whole pallet was "
                   + (f"held" if mix["Location"] in ON_SITE else f"recalled from {mix['Customer']}") + f" even though {b0} is clear.")
    L += ["", "Set aside:",
          f"- Lot {LOT} from {', '.join(twin)} is a different lot: AL-3 1 identifies a lot by supplier and lot code together. Harrowgate Spice lot HS-24871 "
          "is a different lot code.",
          "- The laboratory's negative sesame results and the technician's request to leave a batch out: AL-3 3, a test clears nothing.",
          "- The commercial director's request not to recall from Brackenmoor Stores: RP-4 applies to every customer alike.",
          "- The Tuesday-night pallet export: a stale snapshot; locations were taken from the pallet stock register when acting.",
          "- Unposted scale tickets: they record nothing until posted (AL-3 2.3, SOP-ST-5 4).",
          "- Ticket corrections: SOP-ST-5 5 lets only a shift lead correct a posted ticket, in a comment. " + cap("; ".join(corr)) + "." + op_txt,
          "- Swabs that do not validate for sesame: SOP-CD-2 4, a Gluten or Milk swab covers that allergen alone, so a Pass on one did not "
          "break carry-over; only Sesame and Total protein swabs do. " + ". ".join(map(cap, wrong_test)) + ("." if wrong_test else "")
          + " SOP-CD-2 5, a clean-down logged as finishing after the next run had started did not lie between the runs, so it did not break "
          "carry-over either. " + ". ".join(map(cap, late_cd)) + ("." if late_cd else ""),
          "- Runs left out because a clean-down did validate between them and an implicated run: " + exc_txt
          + (f"; and {len(exc) - 4} further runs were left out the same way." if len(exc) > 4 else ".")
          + " A validating Pass ends the chain there, so nothing downstream of it was traced through that line.",
          "- The supplier notice says the second part-delivery travelled as HS-24817-2; it is the same lot and was traced with it.",
          "- Sacks: the lot's goods receipts record a 20 kg sack, so its bag tickets were converted at 20 kg, not the 25 kg default (SOP-ST-5 3).",
          "- Locations: the Ridgeway cold store is a Kestrel Fold site, so pallets there were held; pallets in transit have left site and were "
          "recalled (RP-4 2 and 3). Mixed pallets were implicated when either batch on them was, whichever of the two it is." + mix_txt,
          "Counts: every stores count in the tub register is a gross weight, so each one was converted to a net weight by subtracting its bin's tare "
          "(SOP-ST-5 7) before the tub was reconciled — the same net figure is what the AL-3 4.3 shortfall test and the on-hand column of the mass "
          "balance are taken from, for every tub of the lot and not only the short one.",
          "Carry-over was decided by SOP-CD-2 3: only a Pass swab validates a clean-down; Pending and Fail do not. The trace was repeated until a pass added nothing (AL-3 2.6). The ticket listing stopped short of its stated count, so tickets "
          "were read by status; the write-off register refused listing, so its records were opened from search; a rate-limited query was retried.",
          "", "Mass balance of lot " + LOT + f" (kg): received {d['mass_balance']['received']}, used {d['mass_balance']['used']}, on hand "
          f"{d['mass_balance']['on_hand']}, written off {d['mass_balance']['waste']}, unaccounted {d['mass_balance']['unaccounted']}."]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
