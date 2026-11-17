"""Seeded production world for the lot-trace task: ten production days at Kestrel Fold Foods, a suspect seasoning lot
planted through decant, bags, blends, rework and line carry-over, and the AL-3 truth computed by tracerules."""
from __future__ import annotations

import random
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from .tracerules import (CleanDown, Container, Pallet, Receipt, Run, Usage, Waste, disposition, mass_balance,
                         trace)

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
DAYS = 10
SUPPLIER, LOT, DECOY_LOT, PART_LOT = "Harrowgate Spice", "HS-24817", "HS-24871", "HS-24817-2"
LOTS = (LOT, PART_LOT)
SUSPECT_SACK_KG = 20
RIDGEWAY, TRANSIT = "Ridgeway cold store", "In transit"
SHIFT_LEADS = ["Ines Halloran", "Dev Okafor", "Ruth Penhale"]
OPERATOR = "Kit Marsh"
TWIN_SUPPLIER = "Dunmere Ingredients"          # uses the same lot code for an unrelated product line
CUSTOMERS = ["Brackenmoor Stores", "Pellow & Finch", "Northgate Co-operative", "Tamsin Rowe Catering", "Ashby Vale Foodservice"]
BASES = {"TIK": "Tikka base", "CHL": "Chilli base", "RAG": "Ragu base", "KOR": "Korma base", "SOU": "Soup base"}
PRODUCTS = {  # finished product -> (base, line)
    "Chicken tikka pots": ("TIK", "L1"), "Vegetable korma": ("KOR", "L1"),
    "Smoky bean chilli": ("CHL", "L2"), "Beef ragu": ("RAG", "L2"),
    "Spiced lentil soup": ("SOU", "L3"), "Pulled pork bowls": ("CHL", "L3"),
}
INGREDIENTS = {"Smoked paprika": ("CHL", "RAG"), "Garlic granules": ("TIK", "RAG", "KOR", "SOU"), "Ground cumin": ("TIK", "CHL", "SOU"),
               "Onion powder": ("RAG", "KOR", "SOU"), "Garam masala": ("TIK", "KOR"), "Chipotle flakes": ("CHL",)}
SUPPLIERS = ["Harrowgate Spice", "Dunmere Ingredients", "Calloway Seasonings"]
TARE = {"Small bin": 2, "Large bin": 3}      # SOP-ST-5: the stores count is gross; each bin type's tare is fixed


def at(day: int, hh: int, mm: int = 0) -> int:
    return day * 1440 + hh * 60 + mm


def iso(m: int) -> str:
    return (T0.replace(hour=0) + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%MZ")


class World:
    def __init__(self, world_seed: int, task_seed: int):
        self.rng = random.Random(world_seed * 1000003 + task_seed)
        self.receipts: list[Receipt] = []
        self.containers: list[Container] = []
        self.runs: list[Run] = []
        self.usages: list[Usage] = []
        self.cleandowns: list[CleanDown] = []
        self.waste: list[Waste] = []
        self.pallets: list[Pallet] = []
        self.ids: set[str] = set()
        self.levers: dict[str, dict] = {}
        self.ticket_notes: list[dict] = []     # comments on scale tickets: shift-lead corrections and an operator's claim
        self.decoys: dict[str, dict] = {}

    def uid(self, prefix: str, lo: int, hi: int) -> str:
        while True:
            x = f"{prefix}-{self.rng.randint(lo, hi)}"
            if x not in self.ids:
                self.ids.add(x)
                return x

    # ------------------------------------------------------------------ stores
    def receive(self, supplier: str, lot: str, ingredient: str, kg: int, tub: int = 50, sack_kg: int = 25) -> list[str]:
        r = Receipt(self.uid("GRN", 10000, 99999), supplier, lot, ingredient, kg, sack_kg)
        self.receipts.append(r)
        out, left = [], kg
        while left > 0:
            c = Container(self.uid("TUB", 1000, 9999), r.id, None, 0, min(tub, left), ingredient)
            self.containers.append(c)
            out.append(c.id)
            left -= tub
        return out

    def background_stores(self):
        self.stock: dict[str, list[str]] = {}
        for ing in INGREDIENTS:
            for _ in range(3):
                sup = self.rng.choice(SUPPLIERS)
                lot = f"{sup[:1]}{sup.split()[1][:1]}-{self.rng.randint(20000, 29999)}"
                if lot in (LOT, DECOY_LOT):
                    continue
                self.stock.setdefault(ing, []).extend(self.receive(sup, lot, ing, self.rng.choice((150, 200, 250))))
        # decoys: the transposed lot from the same supplier, and the same lot code from another supplier
        self.decoys["transposed"] = {"containers": self.receive(SUPPLIER, DECOY_LOT, "Smoked paprika", 200)}
        self.decoys["twin_supplier"] = {"containers": self.receive(TWIN_SUPPLIER, LOT, "Smoked paprika", 150)}
        self.stock["Smoked paprika"].extend(self.decoys["transposed"]["containers"] + self.decoys["twin_supplier"]["containers"])

    # ------------------------------------------------------------------ production
    def schedule(self):
        rng = self.rng
        self.blend_of: dict[str, list[Run]] = {}
        order, off = sorted(BASES), rng.randrange(len(BASES))
        rng.shuffle(order)
        for d in range(DAYS):
            # three of the five bases a day in rotation, so every base is blended at least three days in five
            bases = [order[(off + 3 * d + k) % len(order)] for k in range(3)]
            for k, b in enumerate(bases):
                r = Run(self.uid("BL", 100, 999), "blend", BASES[b], "BR", at(d, 6 + 3 * k), at(d, 8 + 3 * k))
                self.runs.append(r)
                self.blend_of.setdefault(b, []).append(r)
                for ing in [i for i, uses in INGREDIENTS.items() if b in uses][:3]:
                    self.usages.append(Usage(r.id, rng.choice(self.stock[ing]), rng.randint(6, 18), "kg", r.start + 5))
            for line in ("L1", "L2", "L3"):
                prods = [p for p, (_, ln) in PRODUCTS.items() if ln == line]
                for k in range(4):
                    p = prods[(d + k) % len(prods)]
                    r = Run(self.uid("FB", 1000, 9999), "batch", p, line, at(d, 6, 30) + 180 * k, at(d, 9, 0) + 180 * k)
                    self.runs.append(r)
                    base = PRODUCTS[p][0]
                    made = [b for b in self.blend_of.get(base, []) if b.end <= r.start]
                    if made:
                        self.usages.append(Usage(r.id, made[-1].id, rng.randint(20, 45), "kg", r.start + 10))
        for line in ("BR", "L1", "L2", "L3"):
            rs = sorted((r for r in self.runs if r.line == line), key=lambda r: r.start)
            for prev, cur in zip(rs, rs[1:]):
                self.cleandowns.append(CleanDown(line, prev.end + 10, "Pass"))

    def line_runs(self, line: str) -> list[Run]:
        return sorted((r for r in self.runs if r.line == line), key=lambda r: r.start)

    def next_run(self, run: Run) -> Run:
        rs = self.line_runs(run.line)
        return rs[rs.index(run) + 1]

    def set_swab(self, after: Run, swab: str, test: str = "Total protein", late: bool = False):
        nxt = self.next_run(after)
        self.cleandowns = [c for c in self.cleandowns if not (c.line == after.line and after.end <= c.at <= nxt.start)]
        self.cleandowns.append(CleanDown(after.line, nxt.start + 25 if late else after.end + 10, swab, test))
        return nxt

    def frontier(self, lines, day_from=0, day_to=99, skip=()):
        """Implicated runs on these lines whose next run is not implicated: places a carry-over lever can bite."""
        t = self._trace()
        stay = self._trace_flipped().implicated
        out = []
        for ln in lines:
            for r in self.line_runs(ln):
                n = self.next_run_or_none(r)
                if (r.id in t.implicated and r.id in stay and n and n.id not in t.implicated and day_from <= r.start // 1440 <= day_to
                        and r.id not in skip and n.id not in skip):
                    out.append(r)
        return out

    def clean_batches(self, lines, day_from, day_to, skip=()):
        """Batches the trace has not reached, followed by a run it has not reached either."""
        t = self._trace()
        return [r for ln in lines for r in self.line_runs(ln) if r.kind == "batch" and r.id not in t.implicated
                and day_from <= r.start // 1440 <= day_to and self.next_run_or_none(r)
                and self.next_run_or_none(r).id not in t.implicated and r.id not in skip]

    def blend(self, base: str, day: int) -> Run:
        return next(b for b in self.blend_of[base] if b.start // 1440 >= day)

    def batches_on(self, line: str, day: int) -> list[Run]:
        return [r for r in self.line_runs(line) if r.start // 1440 == day]

    # ------------------------------------------------------------------ the suspect lot
    def plant(self):
        rng = self.rng
        s1 = self.receive(SUPPLIER, LOT, "Smoked paprika", 300, tub=100, sack_kg=SUSPECT_SACK_KG)
        s2 = self.receive(SUPPLIER, LOT, "Smoked paprika", 150, tub=150, sack_kg=SUSPECT_SACK_KG)
        cf = self.receive(SUPPLIER, PART_LOT, "Smoked paprika", 50, tub=50, sack_kg=SUSPECT_SACK_KG)[0]
        ca, cb, cc = s1
        cd = s2[0]
        # bags: tub ca goes into a chilli blend on day 0 by the kilo and a ragu blend on day 3 by the bag
        b0 = self.blend("CHL", 0)
        b3 = self.blend("RAG", 3)
        self.usages += [Usage(b0.id, ca, 18, "kg", b0.start + 6), Usage(b3.id, ca, 2, "bag", b3.start + 6)]
        self.levers["bags"] = {"container": ca, "run": b3.id, "bags": 2}
        # decant: tub cb emptied into a fresh tub, which goes into a soup blend on day 5 and a lentil soup batch on day 6
        ce = Container(self.uid("TUB", 1000, 9999), None, cb, 0, 100, "Smoked paprika")
        self.containers.append(ce)
        b5 = self.blend("SOU", 5)
        f6 = next(r for r in self.batches_on("L3", 6) if r.product == "Spiced lentil soup")
        self.usages += [Usage(b5.id, ce.id, 15, "kg", b5.start + 6), Usage(f6.id, ce.id, 8, "kg", f6.start + 12)]
        self.levers["decant"] = {"from": cb, "to": ce.id, "runs": [b5.id, f6.id]}
        # cc never opened; cd: one bag into a chilli blend on day 7, 12 kg spilled and written off
        b7 = self.blend("CHL", 7)
        self.usages.append(Usage(b7.id, cd, 1, "bag", b7.start + 6))
        self.waste.append(Waste(cd, 12))
        short = rng.randint(11, 16)
        self.levers["mass_balance"] = {"short_kg": short}
        self.capacity = {ca: 100, cc: 100, ce.id: 100, cd: 150, cf: 50}
        # carry-over: the blend room run after the day-0 chilli blend follows a Pending swab (implicated) ...
        nxt = self.set_swab(b0, "Pending")
        self.levers["carry_pending"] = {"after": b0.id, "run": nxt.id}
        # ... after the day-3 ragu blend the swab is Pass (next blend clean) ...
        self.levers["carry_pass"] = {"after": b3.id, "run": self.set_swab(b3, "Pass").id}
        # ... and on L2 a Fail swab after the first implicated batch
        self.suspect = {ca, cb, cc, cd, ce.id, cf}
        t = self._trace()
        l2 = [r for r in self.line_runs("L2") if r.id in t.implicated and self.next_run_or_none(r)
              and self.next_run_or_none(r).id not in t.implicated]
        fail_after = l2[0]
        self.levers["carry_fail"] = {"after": fail_after.id, "run": self.set_swab(fail_after, "Fail").id}
        # rework: an implicated chilli batch's leftovers go into a later pulled pork batch two days on, which is
        # followed by a Pending swab, so the carry-over chain only appears once the rework has been traced
        t = self._trace()
        src = next(r for r in self.line_runs("L2") if r.id in t.implicated and r.product == "Smoky bean chilli")
        day = src.start // 1440 + 2
        cand = [r for r in self.line_runs("L3") if r.start // 1440 >= day and r.id not in t.implicated
                and self.next_run_or_none(r) and self.next_run_or_none(r).id not in t.implicated]
        dst = cand[0]
        self.usages.append(Usage(dst.id, src.id, 30, "kg", dst.start + 15))
        self.levers["rework"] = {"from": src.id, "to": dst.id, "kg": 30}
        self.levers["rework_carry"] = {"after": dst.id, "run": self.set_swab(dst, "Pending").id}
        # fixpoint: the batch the Fail swab lets carry-over reach is reworked into a later batch on another line, so that batch
        # is found only by a second pass over the records (usage after carry-over)
        t = self._trace()
        fsrc = next(r for r in self.runs if r.id == self.levers["carry_fail"]["run"])
        fcand = [r for r in self.line_runs("L1") + self.line_runs("L3") if r.start > fsrc.end + 720 and r.id not in t.implicated
                 and self.next_run_or_none(r) and self.next_run_or_none(r).id not in t.implicated]
        fdst = min(fcand, key=lambda r: r.start)
        self.usages.append(Usage(fdst.id, fsrc.id, 20, "kg", fdst.start + 15))
        self.levers["fixpoint_rework"] = {"from": fsrc.id, "to": fdst.id, "kg": 20}
        # decoy rework from a clean batch, so "every rework is implicated" is wrong
        t = self._trace()
        clean = [r for r in self.runs if r.kind == "batch" and r.id not in t.implicated and r.start // 1440 < DAYS - 2]
        csrc = clean[0]
        cdst = next(r for r in self.line_runs("L1") if r.start > csrc.end + 1440 and r.id not in t.implicated)
        self.usages.append(Usage(cdst.id, csrc.id, 25, "kg", cdst.start + 15))
        self.decoys["clean_rework"] = {"from": csrc.id, "to": cdst.id}
        used_runs = {x for v in self.levers.values() for x in v.values() if isinstance(x, str)}
        # part-delivery: the notice names HS-24817-2; its only tub goes straight into a batch nothing else reaches
        w = rng.choice(self.clean_batches(("L2", "L3"), 3, 6, used_runs))
        self.usages.append(Usage(w.id, cf, 6, "kg", w.start + 12))
        self.levers["part_delivery"] = {"lot": PART_LOT, "container": cf, "run": w.id}
        used_runs.add(w.id)
        # shift-lead correction that adds: the ticket was keyed against a decoy tub; the corrected source is suspect tub ca
        x = rng.choice(self.clean_batches(("L1",), 4, 6, used_runs))
        wrong = self.decoys["transposed"]["containers"][0]
        u = Usage(x.id, ca, 5, "kg", x.start + 14)
        self.usages.append(u)
        self.ticket_notes.append({"usage": u, "recorded_source": wrong, "author": SHIFT_LEADS[0], "kind": "correction_adds",
                                  "text": f"Keyed against the wrong tub. This draw came from {ca}, not {wrong}. Corrected source: {ca}."})
        self.levers["comment_adds"] = {"run": x.id, "recorded": wrong, "actual": ca}
        used_runs.add(x.id)
        # shift-lead correction that removes: the ticket says suspect tub cd; the draw came from a clean tub
        y = rng.choice(self.clean_batches(("L3",), 6, 8, used_runs))
        clean_tub = self.stock["Ground cumin"][0]
        u = Usage(y.id, clean_tub, 4, "kg", y.start + 14)
        self.usages.append(u)
        self.ticket_notes.append({"usage": u, "recorded_source": cd, "author": SHIFT_LEADS[1], "kind": "correction_removes",
                                  "text": f"Scanned the wrong label. Nothing came out of {cd} on this run; the 4 kg was ground cumin from {clean_tub}. Corrected source: {clean_tub}."})
        self.levers["comment_removes"] = {"run": y.id, "recorded": cd, "actual": clean_tub}
        used_runs.add(y.id)
        # an operator's comment claiming a correction: no authority under SOP-ST-5, so it changes nothing
        z = rng.choice(self.clean_batches(("L1", "L2"), 2, 8, used_runs))
        zu = next(v for v in self.usages if v.run == z.id)
        self.ticket_notes.append({"usage": zu, "recorded_source": zu.source, "author": OPERATOR, "kind": "operator_claim",
                                  "text": f"I think this was really out of {ca}, the labels were mixed up that morning."})
        self.decoys["operator_comment"] = {"run": z.id, "claimed": ca}
        used_runs.add(z.id)
        # swab test type: a Gluten Pass and a Milk Pass validate nothing for sesame; a Sesame Pass does
        g = rng.choice(self.frontier(("L1", "L3"), 0, 8, used_runs))
        self.levers["swab_gluten"] = {"after": g.id, "run": self.set_swab(g, "Pass", "Gluten").id}
        used_runs |= {g.id, self.levers["swab_gluten"]["run"]}
        m = rng.choice(self.frontier(("L1", "L2", "L3"), 0, 8, used_runs))
        self.levers["swab_milk"] = {"after": m.id, "run": self.set_swab(m, "Pass", "Milk").id}
        used_runs |= {m.id, self.levers["swab_milk"]["run"]}
        # a Total-protein Pass logged as finished after the next run had started does not lie between the runs
        lt = rng.choice(self.frontier(("L1", "L2", "L3"), 0, 8, used_runs))
        self.levers["swab_logged_late"] = {"after": lt.id, "run": self.set_swab(lt, "Pass", "Total protein", late=True).id}
        used_runs |= {lt.id, self.levers["swab_logged_late"]["run"]}
        sp = rng.choice(self.frontier(("L1", "L2", "L3"), 0, 8, used_runs))
        self.decoys["swab_sesame_pass"] = {"after": sp.id, "run": self.set_swab(sp, "Pass", "Sesame").id}
        # mid-run change m1: a scale ticket keyed late posts part of tub cd's shortfall into an L1 batch the trace had not reached
        t = self._trace()
        # placed within a day after tub cd's other draw (the day-7 chilli blend), so the AL-3 4.3 window it opens is narrow
        paprika = {name for name, ings in recipes().items() if "Smoked paprika" in ings}

        def window_blends(r):
            lo, hi = sorted((b7.start + 6, r.start + 20))
            return [x for x in self.runs if x.kind == "blend" and lo <= x.start <= hi and x.product in paprika]
        cands = sorted((r for ln in ("L1", "L3", "L2") for r in self.line_runs(ln) if b7.end < r.start <= b7.start + 2880
                        and r.id not in t.implicated and r.id not in used_runs and self.next_run_or_none(r)
                        and self.next_run_or_none(r).id not in t.implicated), key=lambda r: r.start)
        tgt = next(r for r in cands if len(window_blends(r)) == 1 and window_blends(r)[0].id not in t.implicated)
        k = rng.randint(5, 8)
        self.late_usage = Usage(tgt.id, cd, k, "kg", tgt.start + 20)
        # size the stores shortfall so that, once the late ticket posts, tub cd is 3 to 5 kg short on its net count: short
        # under AL-3 4.3 only when the Large bin's 3 kg tare is taken off the gross count
        short = k + rng.randint(3, 5)
        self.levers["mass_balance"] = {"short_kg": short}
        self.levers["late_ticket"] = {"run": tgt.id, "container": cd, "kg": k}
        # mid-run change m2: the Pending swab after the day-0 chilli blend returns Pass, so that carry-over chain is released
        self.levers["swab_flip"] = {"line": "BR", "after": b0.id, "run": self.levers["carry_pending"]["run"]}
        sack = {r.id: r.sack_kg for r in self.receipts}
        root = {c.id: (c.receipt or next(x.receipt for x in self.containers if x.id == c.decant_from)) for c in self.containers
                if c.id in self.suspect}
        drawn = {c: sum(u.qty * (sack[root[c]] if u.unit == "bag" else 1) for u in self.usages if u.source == c) for c in self.capacity}
        wasted = {c: sum(x.kg for x in self.waste if x.container == c) for c in self.capacity}
        on_hand = {c: cap - drawn[c] - wasted[c] - (short if c == cd else 0) for c, cap in self.capacity.items()}
        assert all(v >= 0 for v in on_hand.values()), on_hand
        self.containers = [Container(c.id, c.receipt, c.decant_from, on_hand.get(c.id, c.on_hand_kg), c.filled_kg, c.ingredient)
                           for c in self.containers]
        # mid-run change m5, after the report is first completed: the laboratory revises a Total protein Pass to Fail
        t = self._trace(True)
        cand = [r for ln in ("L1", "L2", "L3") for r in self.line_runs(ln) if r.id in t.implicated and self.next_run_or_none(r)
                and self.next_run_or_none(r).id not in t.implicated and r.id not in used_runs]
        for r in cand:
            n = self.next_run_or_none(r)
            cd_ = [c for c in self.cleandowns if c.line == r.line and r.end <= c.at <= n.start]
            if len(cd_) == 1 and cd_[0].swab == "Pass" and cd_[0].test == "Total protein":
                self.levers["swab_revised"] = {"after": r.id, "run": n.id, "line": r.line, "at": cd_[0].at}
                break

    def next_run_or_none(self, run: Run):
        rs = self.line_runs(run.line)
        i = rs.index(run)
        return rs[i + 1] if i + 1 < len(rs) else None

    def _trace(self, after: bool = False, revised: bool = None):
        usages, cds = self.usages, self.cleandowns
        if after:
            usages = usages + [self.late_usage]
            b0 = next(r for r in self.runs if r.id == self.levers["swab_flip"]["after"])
            cds = [CleanDown(c.line, c.at, "Pass", c.test) if c.line == "BR" and c.at == b0.end + 10 else c for c in cds]
            rv = self.levers.get("swab_revised")
            if rv and (revised is None or revised):
                cds = [CleanDown(c.line, c.at, "Fail", c.test) if c.line == rv["line"] and c.at == rv["at"] else c for c in cds]
        return trace(LOTS, SUPPLIER, self.receipts, self.containers, self.runs, usages, cds, self.waste, recipes())

    def _trace_flipped(self):
        """The trace with the day-0 blend-room Pending swab already returned Pass (mid-run change m2)."""
        b0 = next(r for r in self.runs if r.id == self.levers["carry_pending"]["after"])
        cds = [CleanDown(c.line, c.at, "Pass", c.test) if c.line == "BR" and c.at == b0.end + 10 else c for c in self.cleandowns]
        return trace(LOTS, SUPPLIER, self.receipts, self.containers, self.runs, self.usages, cds, self.waste, recipes())

    def found_pallet(self):
        """Mid-run change m3: a pallet of a batch implicated before and after the changes, booked as shipped, is found in the chiller."""
        both = self._trace().implicated & self._trace(True).implicated
        p = next(p for p in sorted(self.pallets, key=lambda p: p.id) if p.batches[0] in both and p.location == "shipped"
                 and len(p.batches) == 1)
        self.levers["found_pallet"] = {"pallet": p.id, "customer_before": p.customer}
        # mid-run change m4: despatch sends a Ridgeway pallet of an implicated batch out to a customer: hold becomes recall
        q = next(p for p in sorted(self.pallets, key=lambda p: p.id) if p.batches[0] in both and p.location == RIDGEWAY
                 and p.id != self.levers.get("ridgeway", {}).get("pallet"))
        self.levers["dispatched_pallet"] = {"pallet": q.id, "customer_after": self.rng.choice(CUSTOMERS)}
        return p

    # ------------------------------------------------------------------ pallets
    def palletise(self):
        rng = self.rng
        for r in self.runs:
            if r.kind != "batch":
                continue
            d = r.start // 1440
            for _ in range(rng.randint(2, 4)):
                if d <= DAYS - 4:
                    loc = "shipped" if rng.random() < 0.85 else rng.choice(("chiller", RIDGEWAY))
                elif d <= DAYS - 2:
                    loc = rng.choice(("shipped", TRANSIT, "dispatch bay", "chiller", RIDGEWAY))
                else:
                    loc = rng.choice(("chiller", "chiller", RIDGEWAY))
                batches = (r.id,)
                if rng.random() < 0.12:   # a mixed pallet: the tail of this batch with the next batch on the line
                    nxt = self.next_run_or_none(r)
                    if nxt:
                        batches = (r.id, nxt.id)
                self.pallets.append(Pallet(self.uid("PAL", 100000, 999999), batches, loc, rng.choice(CUSTOMERS) if loc in ("shipped", TRANSIT) else ""))
        # guarantee each pallet lever exists at least once among implicated batches (before and after the changes)
        both = self._trace().implicated & self._trace(True).implicated
        imp_b = sorted(b for b in both if b.startswith("FB-"))
        def force(pred, make, n):
            have = [p for p in self.pallets if pred(p)]
            for p in [p for p in self.pallets if p.batches[0] in imp_b and len(p.batches) == 1 and p.location == "chiller"][:max(0, n - len(have))]:
                i = self.pallets.index(p)
                self.pallets[i] = make(p)
        force(lambda p: p.location == RIDGEWAY and any(b in both for b in p.batches), lambda p: Pallet(p.id, p.batches, RIDGEWAY, ""), 3)
        force(lambda p: p.location == TRANSIT and any(b in both for b in p.batches), lambda p: Pallet(p.id, p.batches, TRANSIT, rng.choice(CUSTOMERS)), 2)
        # mixed pallets whose first batch is clean and second implicated: only reading both batches catches them
        clean_b = [r for r in self.runs if r.kind == "batch" and r.id not in self._trace().implicated and r.id not in self._trace(True).implicated]
        hits = [p for p in self.pallets if len(p.batches) == 2 and p.batches[0] not in both and p.batches[1] in both]
        for r in clean_b:
            if len(hits) >= 3:
                break
            n = self.next_run_or_none(r)
            if n and n.id in both:
                p = next((p for p in self.pallets if p.batches == (r.id,)), None)
                if p:
                    i = self.pallets.index(p)
                    self.pallets[i] = Pallet(p.id, (r.id, n.id), p.location, p.customer)
                    hits.append(self.pallets[i])
        self.levers["mixed_pallets"] = {"pallets": sorted(p.id for p in hits)}
        self.levers["ridgeway"] = {"pallet": sorted(p.id for p in self.pallets if p.location == RIDGEWAY and any(b in both for b in p.batches))[0]}


def recipes() -> dict:
    """Blend product -> the ingredients its recipe uses (the blend room weighs the first three of them)."""
    return {name: [i for i, uses in INGREDIENTS.items() if b in uses][:3] for b, name in BASES.items()}


def truth(w: World, after: bool, revised: bool = None) -> dict:
    t = w._trace(after, revised)
    pallets = w.pallets
    if after:
        fp, dp = w.levers["found_pallet"]["pallet"], w.levers["dispatched_pallet"]
        pallets = [Pallet(p.id, p.batches, "chiller", "") if p.id == fp else
                   Pallet(p.id, p.batches, TRANSIT, dp["customer_after"]) if p.id == dp["pallet"] else p for p in pallets]
    batches, held, recall = disposition(t, w.runs, pallets)
    suspect_receipts = {r.id for r in w.receipts if r.lot in LOTS and r.supplier == SUPPLIER}
    usages = w.usages + ([w.late_usage] if after else [])
    mb = mass_balance(suspect_receipts, w.receipts, w.containers, usages, w.waste)
    tubs = sorted(c.id for c in w.containers if c.id in t.implicated and c.on_hand_kg > 0)
    return {"implicated": sorted(t.implicated), "why": t.why, "batches": batches,
            "blends": sorted(r.id for r in w.runs if r.kind == "blend" and r.id in t.implicated),
            "held": held, "recall": recall, "quarantine": tubs, "mass_balance": mb}


def build(world_seed: int, task_seed: int) -> dict:
    w = World(world_seed, task_seed)
    w.background_stores()
    w.schedule()
    w.plant()
    w.palletise()
    w.found_pallet()
    before, after = truth(w, False), truth(w, True)
    truth_mid = truth(w, True, revised=False)
    assert len(before["held"]) >= 20, "the hold triggers need twenty holds in the pre-change world"
    suspect_receipts = sorted(r.id for r in w.receipts if r.lot in LOTS and r.supplier == SUPPLIER)
    notes = [{"run": n["usage"].run, "source": n["usage"].source, "qty": n["usage"].qty, "unit": n["usage"].unit, "at": n["usage"].at,
              "recorded_source": n["recorded_source"], "author": n["author"], "kind": n["kind"], "text": n["text"]} for n in w.ticket_notes]
    return {
        "seeds": {"world": world_seed, "task": task_seed},
        "suspect": {"supplier": SUPPLIER, "lot": LOT, "lots": list(LOTS), "ingredient": "Smoked paprika", "receipts": suspect_receipts},
        "shift_leads": SHIFT_LEADS, "operator": OPERATOR,
        "receipts": [asdict(x) for x in w.receipts], "containers": [asdict(x) for x in w.containers],
        "runs": [asdict(x) for x in w.runs], "usages": [asdict(x) for x in w.usages], "late_usage": asdict(w.late_usage),
        "ticket_notes": notes,
        "cleandowns": [asdict(x) for x in w.cleandowns], "waste": [asdict(x) for x in w.waste],
        "pallets": [asdict(x) for x in w.pallets],
        "levers": w.levers, "decoys": w.decoys, "recipes": recipes(), "tare": TARE,
        "truth_completed_once": truth_mid,
        "truth_before": before, "truth": after,
    }
