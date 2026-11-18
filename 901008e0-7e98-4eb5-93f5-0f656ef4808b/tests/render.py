"""Render the judge's two inputs: the reference (at verifier build) and the run's own state (at verify time).

python render.py reference <plan.json> <out.md>
python render.py state <out.md>        (reads the same paths as test_outputs.py)
"""
import json
import sys

WORD = {"usage": "took", "carry": "carry-over from", "decant": "decanted from", "receipt": "filled from",
        "presumed": "presumed (AL-3 4.3) to have taken from short tub"}


def route(node, why, depth=0):
    w = why.get(node)
    if w is None or depth > 40:
        return node
    if w == "receipt":
        return f"{node} (receipt of the lot)"
    kind, src = w.split(":", 1)
    return f"{node} {WORD[kind]} {route(src, why, depth + 1)}"


def reference(plan_path, out):
    p = json.load(open(plan_path))
    t, b, lv = p["truth"], p["truth_before"], p["levers"]
    L = ["# Reference: trace TR-2026-031, Harrowgate Spice smoked paprika lot HS-24817", "",
         f"Implicated finished batches after the plant's changes ({len(t['batches'])}), each with a route:"]
    L += [f"- {route(x, t['why'])}" for x in t["batches"]]
    L += ["", f"Tubs to quarantine: {', '.join(t['quarantine'])}.", f"Pallets held: {len(t['held'])}. Pallets recalled: {sum(map(len, t['recall'].values()))}, "
          "one request per customer: " + "; ".join(f"{c} {len(v)}" for c, v in sorted(t["recall"].items())) + ".",
          "", "Changes during the run:",
          f"- Unposted scale ticket {p['ticket_late']} is posted: {lv['late_ticket']['kg']} kg from {lv['late_ticket']['container']} into "
          f"{lv['late_ticket']['run']}, adding that batch and moving unaccounted from {b['mass_balance']['unaccounted']} kg to {t['mass_balance']['unaccounted']} kg.",
          f"- The Pending swab after blend {lv['swab_flip']['after']} returns Pass; batches leaving the trace: "
          f"{', '.join(sorted(set(b['batches']) - set(t['batches'])))}; their held pallets are set Released.",
          f"- Pallet {lv['found_pallet']['pallet']}, booked as shipped to {lv['found_pallet']['customer_before']}, is found in the chiller: held, not recalled.",
          f"- Pallet {lv['dispatched_pallet']['pallet']}, held at the Ridgeway cold store, goes in transit to {lv['dispatched_pallet']['customer_after']}: "
          "it changes from Held to Recall requested and joins that customer's recall request.",
          "", "Ticket comments: " + "; ".join(f"{n['author']} on the ticket for {n['run']}: {n['text']}" + (" (operator: no authority, set aside)" if n['kind'] == "operator_claim" else "")
                                          for n in p["ticket_notes"]) + ".",
          f"Swab levers: a Gluten Pass after {lv['swab_gluten']['after']} and a Milk Pass after {lv['swab_milk']['after']} do not validate for sesame, so "
          f"{lv['swab_gluten']['run']} and {lv['swab_milk']['run']} are implicated by carry-over; a Total protein Pass logged as finishing after "
          f"{lv['swab_logged_late']['run']} started does not lie between the runs, so {lv['swab_logged_late']['run']} is implicated.",
          f"Part-delivery HS-24817-2 is the same lot; its tub {lv['part_delivery']['container']} went into {lv['part_delivery']['run']}. The lot's sacks weigh 20 kg.",
          "AL-3 4.3: " + "; ".join(f"blend {k} is presumed to have taken from short tub {v.split(':', 1)[1]} (its shortfall exceeds 2 kg on net counts, and the window between the tub's first and last posted draw opens once the late ticket posts)" for k, v in t["why"].items() if v.startswith("presumed:")) + ". Stores counts are gross; net = count less the bin's tare (Small 2 kg, Large 3 kg).",
          f"After the report is first completed, the laboratory revises the Total protein swab after {lv['swab_revised']['after']} from Pass to Fail, so {lv['swab_revised']['run']} is implicated by carry-over; the report must be set back to Open, the new pallets held or recalled (additional recall requests), and completed again.",
          "Ridgeway cold store is a Kestrel Fold site (hold); In transit has left site (recall). Mixed pallets: " + ", ".join(lv["mixed_pallets"]["pallets"]) + ".",
          "", "Records to set aside: the same lot code from Dunmere Ingredients (a different supplier); Harrowgate lot HS-24871 (a different code); "
          "negative sesame tests and the technician's request (AL-3 3); the commercial director's request to spare Brackenmoor Stores; the stale Tuesday "
          "pallet export; unposted tickets until posted.",
          "Rules: carry-over unless a clean-down with a Pass on a Sesame or Total protein swab finished between the runs (SOP-CD-2 3 to 5); a bag is the receipt's sack weight (SOP-ST-5 3); decants followed "
          "(AL-3 2.2); rework followed (2.4); repeat to a fixpoint (2.6).",
          "", "Mass balance (kg): " + ", ".join(f"{k} {v}" for k, v in t["mass_balance"].items()) + "."]
    open(out, "w").write("\n".join(L) + "\n")


def state(out):
    import test_outputs as t
    r = t.run()
    counts = {}
    for p, row in r.pallet.items():
        counts[row.get("Status")] = counts.get(row.get("Status"), 0) + 1
    L = ["# End state of the run", "", "Pallet statuses: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda x: str(x[0]))),
         "Quarantined tubs: " + ", ".join(sorted(k for k, v in r.tub.items() if v.get("Status") == "Quarantined")),
         "Trace report: " + json.dumps({k: v for k, v in r.report.items() if not k.startswith("_")}, sort_keys=True), "", "Mail sent:"]
    L += [f"- to {m.get('to_addr')}: {m.get('subject')} ({len(t.PALLET_LINE.findall(m.get('body', '')))} pallet lines)" for m in r.sent]
    open(out, "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "reference":
        reference(sys.argv[2], sys.argv[3])
    else:
        state(sys.argv[2])
