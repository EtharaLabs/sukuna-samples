"""Findings from what the agent can see: the Notion records and what each piece of media says.

records: {"crew": [props], "roster": [props], "actuals": [props]} with Notion property values unwrapped.
media: {"techlog": [...], "scans": [...], "voice": [...]} as read from the photographs, scans and notes.
Returns ftl.Finding objects for the in-scope crew under the revision in force for each duty.
"""
from __future__ import annotations

from ftl import Duty, audit, to_min

KIND = {"Flight duty": "FDP", "Airport standby": "AIRPORT_SB", "Home standby": "HOME_SB"}


def in_scope(crew: list[dict]) -> set[str]:
    return {c["Staff number"] for c in crew if c["Rank"] in ("Captain", "First Officer") and c["Fleet"] == "E190" and c["Base"] == "ABZ"}


def derive(records: dict, media: dict) -> list:
    scope = in_scope(records["crew"])
    tl = {}
    for t in media["techlog"]:
        tl.setdefault(t["duty"], t)
    scans = {s["duty"]: s for s in media["scans"]}
    callouts = {v["duty"]: v for v in media["voice"] if v["kind"] == "callout"}
    terminal = {v["duty"]: v for v in media["voice"] if v["kind"] == "ambience" and v["ambience"] == "terminal"}
    route = {r["Duty ref"]: r.get("Route", "") for r in records["roster"]}
    duties = []
    for a in records["actuals"]:
        staff = a["Staff number"]
        if staff not in scope:
            continue
        ref = a["Duty ref"]
        kind = KIND[a["Type"]]
        evidence = []
        if kind != "FDP":
            if ref in terminal:
                kind = "AIRPORT_SB"
                evidence.append(terminal[ref]["id"])
            duties.append(Duty(ref, staff, kind, to_min(a["Report (UTC)"]), to_min(a["End (UTC)"]), evidence=tuple(evidence)))
            continue
        report = to_min(a["Report (UTC)"])
        on = to_min(a["On-blocks last sector (UTC)"])
        sectors = int(a["Sectors"])
        positioning = False
        page = tl.get(ref)
        if page:
            true_on, true_sectors = page["legs"][-1]["on"], len(page["legs"])
            if true_on != on or true_sectors != sectors:
                on, sectors = true_on, true_sectors
                evidence.append(page["id"])
        if ref in callouts:
            v = callouts[ref]
            report = to_min(v["sign_on"])
            positioning = True
            evidence.append(v["id"])
        scan = scans.get(ref)
        filed = bool(scan and scan.get("signed"))
        if filed and a.get("Discretion used") != "Yes":
            evidence.append(scan["id"])
        duties.append(Duty(ref, staff, "FDP", report, on, sectors=sectors, positioning=positioning,
                           away=bool(route.get(ref)) and route[ref].split("-")[-1] != "ABZ", discretion_filed=filed, evidence=tuple(evidence)))
    return audit(duties)
