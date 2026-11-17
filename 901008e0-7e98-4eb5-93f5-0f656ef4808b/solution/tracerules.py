"""AL-3 trace rules: forward closure from a suspect supplier lot, line carry-over, disposition and mass balance.

Pure functions over plain records, shared by the generator (truth) and the oracle (derive).
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SACK_KG = 25
ON_SITE = ("chiller", "dispatch bay", "Ridgeway cold store")
VALIDATING_TESTS = ("Sesame", "Total protein")
SHORTFALL_KG = 2                     # AL-3 4.3: a tub of the lot more than this far below its expected net is short


@dataclass(frozen=True)
class Receipt:
    id: str
    supplier: str
    lot: str
    ingredient: str
    kg: int
    sack_kg: int = DEFAULT_SACK_KG


@dataclass(frozen=True)
class Container:
    id: str
    receipt: str | None          # receipt it was filled from
    decant_from: str | None      # or the container it was decanted from
    on_hand_kg: int              # net weight still in stores at trace time (stores count less the bin's tare)
    filled_kg: int = 0           # net weight put into the tub when it was filled or decanted into
    ingredient: str = ""


@dataclass(frozen=True)
class Run:
    id: str
    kind: str                    # "blend" or "batch"
    product: str
    line: str
    start: int                   # minutes from epoch
    end: int


@dataclass(frozen=True)
class Usage:
    run: str
    source: str                  # container, blend or (rework) batch id, as corrected by a shift lead
    qty: int
    unit: str                    # "kg" or "bag"
    at: int


@dataclass(frozen=True)
class CleanDown:
    line: str
    at: int
    swab: str                    # "Pass", "Pending" or "Fail"
    test: str = "Total protein"  # what the swab was tested for
    id: str = ""                 # the swab's identifier, kept so a trace can say which swab it relied on
    when: str = ""               # the finish time exactly as the clean-down register logged it

    @property
    def validates(self) -> bool:
        return self.swab == "Pass" and self.test in VALIDATING_TESTS


@dataclass(frozen=True)
class Waste:
    container: str
    kg: int


@dataclass(frozen=True)
class Pallet:
    id: str
    batches: tuple               # one batch, or two on a mixed pallet
    location: str                # on site (ON_SITE), "In transit" or "shipped"
    customer: str


@dataclass
class Trace:
    implicated: set = field(default_factory=set)
    why: dict = field(default_factory=dict)   # node -> "usage:<src>" | "carry:<prev run>" | "receipt" | "decant:<src>"
    valid: dict = field(default_factory=dict)      # line -> the clean-downs on it that validate (Pass on a sesame-covering test)
    gap: dict = field(default_factory=dict)        # run -> what lay between it and the run before it on its line
    excluded: dict = field(default_factory=dict)   # run kept out of the trace -> the validating clean-down that kept it out


def shortfalls(lot_tubs, containers, usages, waste, receipts) -> dict:
    """Per tub of the lot: expected net (filled - decanted out - posted draws - write-offs) less the counted net."""
    sack = {r.id: r.sack_kg for r in receipts}
    out = {}
    for c in containers:
        if c.id not in lot_tubs:
            continue
        root = root_receipt(c.id, containers)
        drawn = sum(u.qty * (sack[root] if u.unit == "bag" else 1) for u in usages if u.source == c.id)
        decanted = sum(x.filled_kg for x in containers if x.decant_from == c.id)
        wasted = sum(w.kg for w in waste if w.container == c.id)
        out[c.id] = c.filled_kg - decanted - drawn - wasted - c.on_hand_kg
    return out


def presumed(lot_tubs, containers, usages, waste, receipts, runs, recipes) -> dict:
    """AL-3 4.3: a short tub is presumed to have gone into every blend whose recipe uses its ingredient, made between the
    tub's first and last posted draw. Returns blend id -> tub."""
    short = {k: v for k, v in shortfalls(lot_tubs, containers, usages, waste, receipts).items() if v > SHORTFALL_KG}
    by = {c.id: c for c in containers}
    out = {}
    for tub in sorted(short):
        draws = sorted(u.at for u in usages if u.source == tub)
        if len(draws) < 2:
            continue
        for r in sorted(runs, key=lambda r: (r.start, r.id)):
            if r.kind == "blend" and draws[0] <= r.start <= draws[-1] and by[tub].ingredient in recipes.get(r.product, ()):
                out.setdefault(r.id, tub)
    return out


def trace(lots, supplier: str, receipts, containers, runs, usages, cleandowns, waste=(), recipes=None) -> Trace:
    """lots: every lot code the supplier's notice names (the lot and its part-deliveries)."""
    t = Trace()
    lots = set(lots)

    def add(node: str, why: str) -> bool:
        if node in t.implicated:
            return False
        t.implicated.add(node)
        t.why[node] = why
        return True

    for r in receipts:
        if r.lot in lots and r.supplier == supplier:
            add(r.id, "receipt")
    by_line = {}
    for r in runs:
        by_line.setdefault(r.line, []).append(r)
    for rs in by_line.values():
        rs.sort(key=lambda r: (r.start, r.id))
    if recipes is not None:
        lot_r = {r.id for r in receipts if r.lot in lots and r.supplier == supplier}
        lot_tubs = {c.id for c in containers if root_receipt(c.id, containers) in lot_r}
        for blend, tub in presumed(lot_tubs, containers, usages, waste, receipts, runs, recipes).items():
            add(blend, f"presumed:{tub}")
    valid = {}
    for c in cleandowns:
        if c.validates:
            valid.setdefault(c.line, []).append(c)
    t.valid = valid
    for line, rs in by_line.items():
        for prev, cur in zip(rs, rs[1:]):
            t.gap[cur.id] = {"prev": prev.id, "line": line,
                             "pass": [c for c in valid.get(line, ()) if prev.end <= c.at <= cur.start],
                             "near": [(c, c.at > cur.start) for c in sorted(cleandowns, key=lambda c: (c.at, c.id))
                                      if c.line == line and prev.end <= c.at <= cur.end and not (c.validates and c.at <= cur.start)]}
    changed = True
    while changed:
        changed = False
        for c in containers:
            src = c.receipt if c.receipt is not None else c.decant_from
            if src in t.implicated:
                changed |= add(c.id, ("receipt:" if c.receipt else "decant:") + src)
        for u in sorted(usages, key=lambda u: (u.at, u.run, u.source)):
            if u.source in t.implicated:
                changed |= add(u.run, f"usage:{u.source}")
        for line, rs in by_line.items():
            for prev, cur in zip(rs, rs[1:]):
                if prev.id in t.implicated and not any(prev.end <= c.at <= cur.start for c in valid.get(line, ())):
                    changed |= add(cur.id, f"carry:{prev.id}")
    for line, rs in by_line.items():
        for prev, cur in zip(rs, rs[1:]):
            if prev.id in t.implicated and cur.id not in t.implicated and t.gap[cur.id]["pass"]:
                t.excluded[cur.id] = {"prev": prev.id, "swab": t.gap[cur.id]["pass"][0]}
    return t


def root_receipt(cid, containers):
    by = {c.id: c for c in containers}
    seen = set()
    while cid in by and cid not in seen:
        seen.add(cid)
        c = by[cid]
        if c.receipt is not None:
            return c.receipt
        cid = c.decant_from
    return None


def disposition(t: Trace, runs, pallets):
    """Held pallets (on site) and recall lines per customer (left site): {customer: {pallet: [implicated batches]}}."""
    batches = {r.id for r in runs if r.kind == "batch" and r.id in t.implicated}
    held, recall = [], {}
    for p in sorted(pallets, key=lambda p: p.id):
        hit = sorted(b for b in p.batches if b in batches)
        if not hit:
            continue
        if p.location in ON_SITE:
            held.append(p.id)
        else:
            recall.setdefault(p.customer, {})[p.id] = hit
    return sorted(batches), held, recall


def mass_balance(suspect_receipts, receipts, containers, usages, waste) -> dict:
    """received = used + on hand + waste + unaccounted, over every container whose root receipt is suspect.
    A bag weighs its goods receipt's sack weight. A decant moves stock between tubs and is neither use nor loss."""
    sack = {r.id: r.sack_kg for r in receipts}
    root = {c.id: root_receipt(c.id, containers) for c in containers}
    mine = {cid for cid, r in root.items() if r in suspect_receipts}
    received = sum(r.kg for r in receipts if r.id in suspect_receipts)
    used = sum(u.qty * (sack[root[u.source]] if u.unit == "bag" else 1) for u in usages if u.source in mine)
    on_hand = sum(c.on_hand_kg for c in containers if c.id in mine)
    wasted = sum(w.kg for w in waste if w.container in mine)
    return {"received": received, "used": used, "on_hand": on_hand, "waste": wasted,
            "unaccounted": received - used - on_hand - wasted}
