"""Findings from what the agent can see: the Notion records and what each piece of media says.

records: {"crew": [props], "roster": [props], "actuals": [props]} with Notion property values unwrapped.
media: {"techlog": [...], "scans": [...], "voice": [...]} as read from the photographs, scans and notes.
Returns ftl.Finding objects for the in-scope crew under the revision in force for each duty.
"""
from __future__ import annotations

from ftl import Duty, audit, to_min

KIND = {"Ward shift": "SHIFT", "On-site on-call": "ONSITE_CALL", "On-call from home": "HOME_CALL"}


def in_scope(crew: list[dict]) -> set[str]:
    return {c["Staff number"] for c in crew if c["Grade"] in ("Charge Nurse", "Staff Nurse") and c["Unit"] == "Acute Medicine" and c["Site"] == "MGH"}


def derive(records: dict, media: dict) -> list:
    scope = in_scope(records["crew"])
    tl = {}
    for t in media["techlog"]:
        tl.setdefault(t["duty"], t)
    scans = {s["duty"]: s for s in media["scans"]}
    callouts = {v["duty"]: v for v in media["voice"] if v["kind"] == "callout"}
    terminal = {v["duty"]: v for v in media["voice"] if v["kind"] == "ambience" and v["ambience"] == "terminal"}
    route = {r["Shift ref"]: r.get("Ward route", "") for r in records["roster"]}
    duties = []
    for a in records["actuals"]:
        staff = a["Staff number"]
        if staff not in scope:
            continue
        ref = a["Shift ref"]
        kind = KIND[a["Type"]]
        evidence = []
        if kind != "SHIFT":
            if ref in terminal:
                kind = "ONSITE_CALL"
                evidence.append(terminal[ref]["id"])
            duties.append(Duty(ref, staff, kind, to_min(a["Start (UTC)"]), to_min(a["End (UTC)"]), evidence=tuple(evidence)))
            continue
        report = to_min(a["Start (UTC)"])
        on = to_min(a["Clock-out last assignment (UTC)"])
        sectors = int(a["Ward assignments"])
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
        if filed and a.get("Extension used") != "Yes":
            evidence.append(scan["id"])
        duties.append(Duty(ref, staff, "SHIFT", report, on, sectors=sectors, positioning=positioning,
                           away=bool(route.get(ref)) and route[ref].split("-")[-1] != "MGH", discretion_filed=filed, evidence=tuple(evidence)))
    return audit(duties)
