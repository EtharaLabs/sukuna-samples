"""Turn the traceability records, as read through the tools, into the AL-3 trace and the RP-4 actions."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from tracerules import CleanDown, Container, Pallet, Receipt, Run, Usage, Waste, disposition, mass_balance, trace

EPOCH = datetime(2026, 11, 2, tzinfo=timezone.utc)
SUPPLIER, LOT = "Harrowgate Spice", "HS-24817"
LOTS = ("HS-24817", "HS-24817-2")            # the supplier notice: the second part-delivery travelled as HS-24817-2
SHIFT_LEADS = ("Ines Halloran", "Dev Okafor", "Ruth Penhale")   # SOP-ST-5 5
TARE = {"Small bin": 2, "Large bin": 3}      # SOP-ST-5 7
CORRECTED = re.compile(r"Corrected source:\s*(\S+?)\.?\s*$")


def minutes(s: str) -> int:
    return int((datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) - EPOCH).total_seconds() // 60)


def corrections(rec: dict) -> dict:
    """Ticket page id -> corrected source, from shift-lead comments only."""
    names = {u["id"]: u.get("name", "") for u in rec.get("users", [])}
    out = {}
    for c in rec.get("comments", []):
        m = CORRECTED.search(c.get("text", ""))
        if m and names.get(c.get("author_id")) in SHIFT_LEADS:
            out[c["parent_page_id"]] = m[1]
    return out


def derive(rec: dict) -> dict:
    receipts = [Receipt(r["GRN"], r["Supplier"], r["Supplier lot"], r["Ingredient"], int(r["Received kg"]), int(r.get("Sack kg") or 25))
                for r in rec["receipts"]]
    def net(t):
        count = int(t.get("Stores count kg") or 0)
        return count - TARE[t["Bin type"]] if count > 0 else 0
    tubs = [Container(t["Tub"], t["Filled from GRN"] or None, t["Decanted from"] or None, net(t), int(t.get("Filled kg") or 0), t.get("Ingredient") or "")
            for t in rec["tubs"]]
    recipes = {r["Blend"]: [x.strip() for x in str(r["Ingredients"]).split(",")] for r in rec["recipes"]}
    runs = [Run(r["Run"], r["Kind"].lower(), r["Product"], r["Line"], minutes(r["Start"]), minutes(r["End"])) for r in rec["runs"]]
    fix = corrections(rec)
    usages = [Usage(k["Run"], fix.get(k["_id"], k["Source"]), int(k["Quantity"]), k["Unit"], minutes(k["Weighed at"]))
              for k in rec["tickets"] if k["Status"] == "Posted"]
    waste = [Waste(w["Tub"], int(w["Written off kg"])) for w in rec["writeoffs"]]
    cds = [CleanDown(c["Line"], minutes(c["Finished"]), c["Result"], c.get("Swab test") or "Total protein",
                     c.get("Swab") or "", c.get("Finished") or "") for c in rec["cleandowns"]]
    pallets = [Pallet(p["Pallet"], tuple(b.strip() for b in p["Batch"].split(",")), p["Location"], p.get("Customer") or "") for p in rec["pallets"]]
    t = trace(LOTS, SUPPLIER, receipts, tubs, runs, usages, cds, waste, recipes)
    batches, held, recall = disposition(t, runs, pallets)
    suspect = {r.id for r in receipts if r.lot in LOTS and r.supplier == SUPPLIER}
    return {"trace": t, "batches": batches, "held": held, "recall": recall, "fix": fix,
            "quarantine": sorted(c.id for c in tubs if c.id in t.implicated and c.on_hand_kg > 0),
            "mass_balance": mass_balance(suspect, receipts, tubs, usages, waste), "runs": {r.id: r for r in runs}}
