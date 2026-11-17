"""World and task layer for the crew flight time limitations audit: a pure function of two seeds.

build(world_seed, task_seed) returns the plan: crew, roster and actual duties for the whole
airline from the look-back start to the end of the block, the planted task layer for the
in-scope crew, the evidence each planted duty needs, the two mid-run triggers and the
reference findings computed after both triggers have fired.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, replace

from . import ftl
from .ftl import Duty, to_iso, to_min

LOOKBACK_FIRST = "2026-08-04"
LAST_DAY = "2026-09-28"
AIRLINE = "Fernhollow Air"
DOMAIN = "fernhollow-air.example"
STATIONS = {"ABZ": "Aberdeen", "EDI": "Edinburgh", "LSI": "Sumburgh", "KOI": "Kirkwall", "SYY": "Stornoway",
            "BHD": "Belfast City", "MAN": "Manchester", "BHX": "Birmingham", "SOU": "Southampton", "NCL": "Newcastle"}
OUTSTATIONS = ("LSI", "KOI", "SYY", "BHD", "MAN", "BHX", "SOU", "NCL")
GIVEN = ("Aileen", "Bram", "Caitrin", "Dougal", "Elspeth", "Fergus", "Greer", "Hamish", "Iona", "Jarrah", "Kenna", "Lachlan",
         "Morven", "Niall", "Orla", "Padraig", "Rhona", "Somhairle", "Tamsin", "Uisdean", "Vaila", "Wallace", "Ysolde", "Zander",
         "Ailsa", "Brodie", "Catriona", "Duncan", "Eilidh", "Finlay", "Gillian", "Hector", "Isla", "Jamie", "Kirsty", "Lorne",
         "Mhairi", "Neve", "Oran", "Peigi", "Ruaridh", "Sorcha", "Torquil", "Una", "Calum", "Shona", "Euan", "Freya")
FAMILY = ("Abernethy", "Balfour", "Cairncross", "Drummond", "Elphinstone", "Forsyth", "Gilchrist", "Halkett", "Inglis",
          "Jardine", "Kinnear", "Lumsden", "Macrae", "Nairn", "Ogilvie", "Pitcairn", "Rintoul", "Sinclair", "Tulloch",
          "Urquhart", "Veitch", "Wishart", "Yuill", "Aitken", "Brodie", "Cheyne", "Dalgleish", "Erskine", "Fordyce",
          "Garvie", "Hogarth", "Imrie", "Kilgour", "Leask", "Moncur", "Ness", "Ormiston", "Petrie", "Rattray", "Spence",
          "Thain", "Wardlaw", "Yorston", "Baird", "Christie", "Dunnet", "Fyfe", "Gauld")
FLEETS = (("E90", "ABZ", "CP", 14), ("E90", "ABZ", "FO", 14), ("E90", "EDI", "CP", 20), ("E90", "EDI", "FO", 20),
          ("AT7", "ABZ", "CP", 44), ("AT7", "ABZ", "FO", 44), ("E95", "ABZ", "CP", 31), ("E95", "ABZ", "FO", 31),
          ("CC", "ABZ", "CC", 160), ("CC", "EDI", "CC", 82))
REGS = {"E90": ("G-FHEA", "G-FHEB", "G-FHEC", "G-FHED", "G-FHEE"), "E95": ("G-FHNA", "G-FHNB", "G-FHNC"),
        "AT7": ("G-FHTA", "G-FHTB", "G-FHTC", "G-FHTD", "G-FHTE", "G-FHTF")}


PRIMARY = {"rest", "core", "image", "edition", "discretion", "no_report", "audio", "late", "compliant_discretion"}
PADS = {"cumulative", "audio_pad", "late_pad"}


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16))


def _day(i: int) -> str:
    return to_iso(to_min(LOOKBACK_FIRST + "T00:00Z") + i * 1440)[:10]


DAYS = [_day(i) for i in range(56)]


def _local(day: str, clock: int) -> int:
    return to_min(day + "T00:00Z") - ftl.LOCAL_OFFSET + clock


def _crew(rng: random.Random) -> list[dict]:
    crew, used = [], set()
    n = 0
    for fleet, base, rank, count in FLEETS:
        for _ in range(count):
            while True:
                staff = f"{rng.randint(30000, 49999)}"
                if staff not in used:
                    used.add(staff)
                    break
            g, f = rng.choice(GIVEN), rng.choice(FAMILY)
            n += 1
            crew.append({"staff": staff, "given": g, "family": f, "rank": rank, "fleet": fleet, "base": base,
                         "email": f"{g.lower()}.{f.lower()}{n % 7 or ''}@{DOMAIN}",
                         "in_scope": fleet == "E90" and base == "ABZ" and rank in ("CP", "FO")})
    return crew


def _route(rng, base, sectors):
    legs, at = [], base
    for i in range(sectors):
        to = base if (i == sectors - 1 and sectors % 2 == 0) else (rng.choice([s for s in OUTSTATIONS if s != at]) if at == base else base)
        legs.append((at, to))
        at = to
    return legs


def _pattern(rng, person, plan_duties):
    """Ordinary roster for one person over 56 days: blocks of 4 to 5 working days and 2 to 4 off."""
    day, i = 0, 0
    while day < 56:
        work = rng.randint(4, 5)
        for k in range(work):
            if day + k >= 56:
                break
            d = DAYS[day + k]
            roll = rng.random()
            ref = f"{person['fleet'][:2]}{'5' if person['fleet'] == 'E95' else ''}-{d[5:7]}{d[8:10]}-{person['base']}-{rng.randint(100, 999)}"
            if roll < 0.12:
                start = _local(d, rng.choice((300, 360, 720)))
                plan_duties.append({"ref": ref, "staff": person["staff"], "kind": "AIRPORT_SB" if roll < 0.05 else "HOME_SB",
                                    "report": start, "end": start + (360 if roll < 0.05 else 480)})
                continue
            clock = rng.choice((335, 345, 380, 420, 465, 540, 600, 690, 780, 850, 900))
            sectors = rng.choice((2, 2, 3, 4, 4))
            block = rng.randint(55, 85)
            report = _local(d, clock)
            legs, t = [], report + 45
            for a, b in _route(rng, person["base"], sectors):
                off = t + rng.randint(0, 15)
                on = off + block + rng.randint(-8, 8)
                legs.append({"from": a, "to": b, "off": off, "on": on, "flight": f"FH{rng.randint(100, 989)}"})
                t = on + rng.randint(30, 45)
            plan_duties.append({"ref": ref, "staff": person["staff"], "kind": "FDP", "report": report, "legs": legs,
                                "reg": rng.choice(REGS.get(person["fleet"], REGS["E90"])),
                                "away": legs[-1]["to"] != person["base"]})
        day += work + rng.randint(2, 4)
        i += 1


def _end(d):
    return d["legs"][-1]["on"] if d["kind"] == "FDP" else d["end"]


def _limit(d, sectors=None, edition=None):
    ed = edition or ftl.edition_at(d["report"])
    return ftl.max_fdp(d["report"], sectors if sectors is not None else len(d["legs"]), ed)


def _stretch(d, target_fdp):
    """Move the last on-blocks so the actual FDP is target_fdp minutes."""
    shift = (d["report"] + target_fdp) - d["legs"][-1]["on"]
    d["legs"][-1]["on"] += shift


def build(world_seed: int, task_seed: int) -> dict:
    rng = _rng("world", world_seed)
    crew = _crew(rng)
    duties: list[dict] = []
    for person in crew:
        if person["fleet"] != "CC":
            _pattern(_rng("roster", world_seed, person["staff"]), person, duties)
    by_staff: dict[str, list[dict]] = {}
    for d in duties:
        d.setdefault("actual", {})
        by_staff.setdefault(d["staff"], []).append(d)
    for ds in by_staff.values():
        ds.sort(key=lambda x: x["report"])
    # Keep the ordinary world compliant: no accidental exceedance in the generated pattern.
    for ds in by_staff.values():
        for prev, d in zip(ds, ds[1:]):
            gap = d["report"] - (_end(prev) + 30)
            if gap < 13 * 60:
                bump = 13 * 60 - gap
                d["report"] += bump
                if d["kind"] == "FDP":
                    for leg in d["legs"]:
                        leg["off"] += bump
                        leg["on"] += bump
                else:
                    d["end"] += bump
    t = _rng("task", task_seed)
    scope = [c for c in crew if c["in_scope"]]
    t.shuffle(scope)
    plant = _Planter(t, scope, by_staff, crew)
    plant.all()
    return plant.finish(duties)


class _Planter:
    def __init__(self, rng, scope, by_staff, crew):
        self.rng, self.scope, self.by_staff, self.crew = rng, scope, by_staff, crew
        self.evidence: list[dict] = []
        self.used: set[str] = set()
        self.next = 0
        self.triggers: dict = {}
        self.notes: list[dict] = []

    def person(self):
        p = self.scope[self.next % len(self.scope)]
        self.next += 1
        return p

    def fdp(self, person, lo="2026-09-01", hi="2026-09-28", clock=None, avoid_amendment=True):
        cands = [d for d in self.by_staff[person["staff"]] if d["kind"] == "FDP" and d["ref"] not in self.used
                 and lo <= ftl.local_day(d["report"]) <= hi]
        if avoid_amendment:
            cands = [d for d in cands if abs(d["report"] - ftl.AMENDMENT_UTC) > 36 * 60]
        if clock is not None:
            banded = [d for d in cands if clock[0] <= ftl.local_clock(d["report"]) <= clock[1]]
            if banded:
                cands = banded
            else:
                d = self.rng.choice(cands)
                shift = (clock[0] + 10) - ftl.local_clock(d["report"])
                d["report"] += shift
                for leg in d["legs"]:
                    leg["off"] += shift
                    leg["on"] += shift
                cands = [d]
        d = self.rng.choice(cands)
        self.used.add(d["ref"])
        self._clear_after(person, d)
        return d

    def _clear_after(self, person, d):
        """Give the next duty enough rest that a planted long FDP does not spill into a rest finding."""
        ds = self.by_staff[person["staff"]]
        i = ds.index(d)
        if i + 1 < len(ds):
            nxt = ds[i + 1]
            need = _end(d) + 30 + 16 * 60 + 300 - nxt["report"]
            if need > 0 and nxt["ref"] not in self.used:
                nxt["report"] += need
                if nxt["kind"] == "FDP":
                    for leg in nxt["legs"]:
                        leg["off"] += need
                        leg["on"] += need
                else:
                    nxt["end"] += need

    def tag(self, d, *tags):
        d["tags"] = tuple(sorted(set(d.get("tags", ())) | set(tags)))

    def all(self):
        for i in range(9):
            p = self.person()
            hi = "2026-09-14" if i < 4 else "2026-09-28"
            lo = "2026-09-01" if i < 4 else "2026-09-16"
            d = self.fdp(p, lo, hi, clock=(300, 359) if i in (4, 5) else None)
            _stretch(d, _limit(d) + self.rng.randint(6, 58))
            self.tag(d, "core")
        self.discretion()
        self.image()
        self.edition()
        self.rest()
        self.cumulative()
        self.audio()
        self.late()
        self.decoys()

    def _scan(self, d, signed=True, kind="discretion"):
        sid = f"CDR-{self.rng.randint(1000, 9999)}"
        d["actual"]["discretion_report"] = sid
        self.evidence.append({"id": sid, "kind": "discretion_scan", "duty": d["ref"], "signed": signed,
                              "extension_end": to_iso(_end(d)), "report": to_iso(d["report"])})
        return sid

    def discretion(self):
        p = self.person()
        d = self.fdp(p)
        ed = ftl.edition_at(d["report"])
        _stretch(d, _limit(d) + ftl.DISCRETION_MAX[ed] + self.rng.randint(8, 40))
        d["actual"]["discretion_used"] = True
        self._scan(d)
        self.tag(d, "discretion")
        p = self.person()
        d = self.fdp(p)
        _stretch(d, _limit(d) + self.rng.randint(30, 80))
        d["actual"]["discretion_used"] = True
        d["actual"]["discretion_report"] = "not filed"
        self.tag(d, "no_report")
        for _ in range(2):
            p = self.person()
            d = self.fdp(p)
            ed = ftl.edition_at(d["report"])
            _stretch(d, _limit(d) + self.rng.randint(15, ftl.DISCRETION_MAX[ed] - 10))
            d["actual"]["discretion_used"] = True
            self._scan(d)
            self.tag(d, "compliant_discretion")

    def image(self):
        p = self.person()
        d = self.fdp(p)
        _stretch(d, _limit(d) + self.rng.randint(12, 40))
        true_on = d["legs"][-1]["on"]
        d["actual"]["ops_on_override"] = true_on - self.rng.randint(45, 70)
        tl = f"TL-{self.rng.randint(10000, 99999)}"
        self.evidence.append({"id": tl, "kind": "techlog", "duty": d["ref"], "reg": d["reg"], "legs": d["legs"]})
        d["evidence"] = (tl,)
        self.tag(d, "image", "corrupted")
        self.corrupted = d["ref"]
        p = self.person()
        d = self.fdp(p)
        while len(d["legs"]) > 4:
            d = self.fdp(p)
        base = d["legs"][-1]
        extra = {"from": base["to"], "to": base["from"], "off": base["on"] + 40, "on": base["on"] + 40 + 50,
                 "flight": base["flight"] + "R"}
        d["legs"].append(extra)
        d["actual"]["ops_sectors_override"] = len(d["legs"]) - 1
        d["actual"]["ops_on_override"] = base["on"]
        if d["report"] + _limit(d) >= _end(d):
            _stretch(d, _limit(d) + self.rng.randint(10, 35))
        tl = f"TL-{self.rng.randint(10000, 99999)}"
        self.evidence.append({"id": tl, "kind": "techlog", "duty": d["ref"], "reg": d["reg"], "legs": d["legs"]})
        d["evidence"] = (tl,)
        self.tag(d, "image", "diversion")
        p = self.person()
        d = self.fdp(p)
        ed = ftl.edition_at(d["report"])
        _stretch(d, _limit(d) + ftl.DISCRETION_MAX[ed] + self.rng.randint(10, 30))
        d["actual"]["discretion_used"] = False
        d["evidence"] = (self._scan(d),)
        self.tag(d, "image", "scan_contradicts")

    def edition(self):
        p = self.person()
        ds = self.by_staff[p["staff"]]
        anchor = min((d for d in ds if d["kind"] == "FDP" and d["ref"] not in self.used),
                     key=lambda d: abs(d["report"] - ftl.AMENDMENT_UTC))
        self.used.add(anchor["ref"])
        shift = (ftl.AMENDMENT_UTC + 20) - anchor["report"]
        anchor["report"] += shift
        for leg in anchor["legs"]:
            leg["off"] += shift
            leg["on"] += shift
        _stretch(anchor, _limit(anchor, edition="Rev 14") + ftl.DISCRETION_MAX["Rev 14"] + self.rng.randint(8, 25))
        anchor["actual"]["discretion_used"] = True
        self._scan(anchor)
        anchor["roster_day"] = "2026-09-14"
        self.tag(anchor, "edition")
        self._clear_after(p, anchor)
        p = self.person()
        ds = self.by_staff[p["staff"]]
        anchor = min((d for d in ds if d["kind"] == "FDP" and d["ref"] not in self.used),
                     key=lambda d: abs(d["report"] - (ftl.AMENDMENT_UTC - 40)))
        self.used.add(anchor["ref"])
        shift = (ftl.AMENDMENT_UTC - 40) - anchor["report"]
        anchor["report"] += shift
        for leg in anchor["legs"]:
            leg["off"] += shift
            leg["on"] += shift
        anchor["positioning"] = True
        rev13 = _limit(anchor, sectors=len(anchor["legs"]), edition="Rev 13")
        _stretch(anchor, rev13 + self.rng.randint(10, 25))
        anchor["roster_day"] = "2026-09-15"
        self.tag(anchor, "edition")
        self._clear_after(p, anchor)

    def rest(self):
        p = self.person()
        ds = self.by_staff[p["staff"]]
        pairs = [(a, b) for a, b in zip(ds, ds[1:]) if a["kind"] == b["kind"] == "FDP" and a["ref"] not in self.used
                 and b["ref"] not in self.used and "2026-09-02" <= ftl.local_day(b["report"]) <= "2026-09-13" and not a["away"]]
        a, b = self.rng.choice(pairs)
        self.used |= {a["ref"], b["ref"]}
        short = ftl.HOME_REST_MIN - self.rng.randint(25, 70)
        shift = (_end(a) + 30 + short) - b["report"]
        b["report"] += shift
        for leg in b["legs"]:
            leg["off"] += shift
            leg["on"] += shift
        self.tag(b, "rest")
        p = self.person()
        ds = self.by_staff[p["staff"]]
        pairs = [(a, b) for a, b in zip(ds, ds[1:]) if a["kind"] == b["kind"] == "FDP" and a["ref"] not in self.used
                 and b["ref"] not in self.used and "2026-09-17" <= ftl.local_day(a["report"]) <= "2026-09-26" and not a["away"]]
        a, b = self.rng.choice(pairs)
        self.used |= {a["ref"], b["ref"]}
        ext = self.rng.randint(35, 70)
        _stretch(a, _limit(a) + ext)
        a["actual"]["discretion_used"] = True
        self._scan(a)
        self.tag(a, "compliant_discretion")
        rest = max(ftl.HOME_REST_MIN, ftl.duty_minutes(_as_duty(a))) + ext - self.rng.randint(10, 30)
        shift = (_end(a) + 30 + rest) - b["report"]
        b["report"] += shift
        for leg in b["legs"]:
            leg["off"] += shift
            leg["on"] += shift
        self.tag(b, "rest")

    def _pad_window(self, person, first, span, extra_minutes, tag):
        ds = self.by_staff[person["staff"]]
        lo = to_min(first + "T00:00Z")
        for d in ds:
            if d["kind"] == "FDP" and lo <= d["report"] < lo + span * 1440 and d["ref"] not in self.used:
                room = _limit(d) - (_end(d) - d["report"]) - 5
                add = min(room, extra_minutes)
                if add > 0:
                    _stretch(d, _end(d) - d["report"] + add)
                    extra_minutes -= add
                    self.used.add(d["ref"])
                    self.tag(d, tag)
            if extra_minutes <= 0:
                return

    def _total(self, person, end_day, span):
        ds = self.by_staff[person["staff"]]
        days = {to_iso(to_min(end_day + "T00:00Z") - i * 1440)[:10] for i in range(span)}
        return sum(ftl.duty_minutes(_as_duty(d)) for d in ds if ftl.local_day(d["report"]) in days)

    def cumulative(self):
        for limit_type, span, limit in ftl.CUMULATIVE:
            p = self.person()
            end_day = {"DUTY_7D": "2026-09-10", "DUTY_14D": "2026-09-19", "DUTY_28D": "2026-09-08"}[limit_type]
            first = to_iso(to_min(end_day + "T00:00Z") - (span - 1) * 1440)[:10]
            need = limit - self._total(p, end_day, span) + self.rng.randint(15, 60)
            if need > 0:
                ds = self.by_staff[p["staff"]]
                lo = to_min(first + "T00:00Z")
                if True:
                    day_free = set(DAYS) - {ftl.local_day(d["report"]) for d in ds}
                    for day in sorted(day_free):
                        if first <= day <= end_day and need > 600:
                            start = _local(day, 600)
                            ref = f"E9-{day[5:7]}{day[8:10]}-ABZ-{self.rng.randint(100, 999)}"
                            sb = {"ref": ref, "staff": p["staff"], "kind": "AIRPORT_SB", "report": start, "end": start + 480, "actual": {}}
                            ds.append(sb)
                            ds.sort(key=lambda x: x["report"])
                            need -= 480
                self._pad_window(p, first, span, need, "cumulative")
            if self._total(p, end_day, span) <= limit:
                raise RuntimeError(f"could not plant {limit_type}")

    def audio(self):
        p = self.person()
        ds = self.by_staff[p["staff"]]
        d = self.fdp(p, "2026-09-16", "2026-09-26", clock=(420, 600))
        call = d["report"] - self.rng.randint(110, 140)
        sb = {"ref": d["ref"].replace(d["ref"][-3:], f"{int(d['ref'][-3:]) % 900 + 50:03d}") + "S", "staff": p["staff"],
              "kind": "HOME_SB", "report": call - 65, "end": call, "actual": {}}
        ds.append(sb)
        ds.sort(key=lambda x: x["report"])
        d["actual"]["ops_report_override"] = d["report"]
        d["report"] = call + 15
        d["positioning"] = True
        _stretch(d, _limit(d, sectors=len(d["legs"]) + 1) + self.rng.randint(8, 30))
        vn = f"VN-{self.rng.randint(100, 999)}"
        self.notes.append({"id": vn, "kind": "callout", "duty": d["ref"], "staff": p["staff"], "call": to_iso(call),
                           "sign_on": to_iso(d["report"]), "from": "Edinburgh", "ambience": "office"})
        d["evidence"] = (vn,)
        self.tag(d, "audio")
        p = self.person()
        ds = self.by_staff[p["staff"]]
        end_day = "2026-09-24"
        first = to_iso(to_min(end_day + "T00:00Z") - 6 * 1440)[:10]
        day_free = sorted(set(DAYS) - {ftl.local_day(d["report"]) for d in ds})
        day = next(x for x in day_free if first <= x <= end_day)
        start = _local(day, 360)
        ref = f"E9-{day[5:7]}{day[8:10]}-ABZ-{self.rng.randint(100, 999)}"
        sb = {"ref": ref, "staff": p["staff"], "kind": "AIRPORT_SB", "report": start, "end": start + 600,
              "actual": {"ops_kind_override": "HOME_SB"}, "tags": ("audio",)}
        ds.append(sb)
        ds.sort(key=lambda x: x["report"])
        vn = f"VN-{self.rng.randint(100, 999)}"
        self.notes.append({"id": vn, "kind": "ambience", "duty": ref, "staff": p["staff"], "call": to_iso(start + 30),
                           "ambience": "terminal"})
        sb["evidence"] = (vn,)
        target = 3600 + self.rng.randint(15, 120)
        need = target - self._total(p, end_day, 7)
        if need > 0:
            self._pad_window(p, first, 7, need, "audio_pad")
        need = target - self._total(p, end_day, 7)
        free = sorted(set(DAYS) - {ftl.local_day(x["report"]) for x in ds})
        for day in free:
            if need <= 0:
                break
            if first <= day <= end_day:
                length = max(120, min(480, need))
                start = _local(day, 720)
                extra = {"ref": f"E9-{day[5:7]}{day[8:10]}-ABZ-{self.rng.randint(100, 999)}", "staff": p["staff"],
                         "kind": "AIRPORT_SB", "report": start, "end": start + length, "actual": {}, "tags": ("audio_pad",)}
                ds.append(extra)
                ds.sort(key=lambda x: x["report"])
                need -= length
        full = self._total(p, end_day, 7)
        if not 3600 < full <= 3600 + 600 - int(600 * ftl.HOME_STANDBY_SHARE):
            raise RuntimeError(f"ambience standby window total {full} cannot separate airport from home standby")
        self.ambience_staff = p["staff"]

    def late(self):
        for _ in range(60):
            p = self.person()
            ds = self.by_staff[p["staff"]]
            pairs = [(a, b) for a, b in zip(ds, ds[1:]) if a["kind"] == b["kind"] == "FDP" and not a["away"]
                     and a["ref"] not in self.used and b["ref"] not in self.used and _limit(a) >= 750
                     and "2026-09-03" <= ftl.local_day(a["report"]) <= "2026-09-12"]
            if pairs:
                break
        a, b = self.rng.choice(pairs)
        self.used |= {a["ref"], b["ref"]}
        gap = self.rng.randint(12, 25)
        _stretch(a, _limit(a) - gap)
        corr = gap + self.rng.randint(10, 30)
        need_pre = max(ftl.HOME_REST_MIN, ftl.duty_minutes(_as_duty(a)))
        shift = (_end(a) + 30 + need_pre - self.rng.randint(10, 30)) - b["report"]
        b["report"] += shift
        for leg in b["legs"]:
            leg["off"] += shift
            leg["on"] += shift
        self.triggers["a"] = {"duty": a["ref"], "on_blocks_before": to_iso(_end(a)), "on_blocks_after": to_iso(_end(a) + corr)}
        a["late_shift"] = corr
        self.tag(a, "late")
        self.tag(b, "late")
        self.late_staff = p["staff"]

    def decoys(self):
        target = self.scope[0]
        twin = next(c for c in self.crew if c["fleet"] == "CC" and c["base"] == "ABZ")
        twin["family"] = target["family"]
        twin["staff"] = target["staff"][:-1] + str((int(target["staff"][-1]) + 1) % 10)
        twin["near_duplicate_of"] = target["staff"]
        self.twin = twin["staff"]

    def _repair(self):
        """Push every unplanned duty that would breach minimum rest later until no unplanned rest finding remains."""
        for staff in [c["staff"] for c in self.scope]:
            ds = self.by_staff[staff]
            for _ in range(200):
                ds.sort(key=lambda x: x["report"])
                bad = None
                for a, b in zip(ds, ds[1:]):
                    if set(b.get("tags", ())) & PRIMARY:
                        continue
                    da, db = _as_duty(a), _as_duty(b)
                    gap = db.report - (da.end + (ftl.POST_FLIGHT if da.kind == "FDP" else 0))
                    need = max(ftl.duty_minutes(da), ftl.AWAY_REST_MIN if da.away else ftl.HOME_REST_MIN) + 150
                    if da.kind != "HOME_SB" and gap < need:
                        bad = (b, need - gap + 30)
                        break
                if not bad:
                    break
                b, shift = bad
                if ftl.local_day(b["report"] + shift) != ftl.local_day(b["report"]) and set(b.get("tags", ())) & PADS:
                    raise RuntimeError(f"rest repair would move padded duty {b['ref']} to another day")
                b["report"] += shift
                if b["kind"] == "FDP":
                    for leg in b["legs"]:
                        leg["off"] += shift
                        leg["on"] += shift
                else:
                    b["end"] += shift

    def late_c(self):
        """Trigger c: one more duty-actuals change, written once the twentieth finding record exists. The duty is
        unphotographed, so no technical-log page contradicts the changed on-blocks, and it adds exactly one FDP finding."""
        from . import emit
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        rng.random()
        all_duties = [d for ds in self.by_staff.values() for d in ds]
        scope_staff = {c["staff"] for c in self.scope}
        manifest = emit.media_manifest({"duties": all_duties, "evidence": self.evidence, "crew": self.crew, "voice_notes": self.notes})
        shown = {e["duty"] for kind in ("techlog", "scans") for e in manifest[kind]}

        def audit():
            return {(f.key, f.excess_min) for f in ftl.audit([_as_duty(d) for d in all_duties if d["staff"] in scope_staff])}

        base = audit()
        flagged = {k[0] for k, _ in base}
        cands = [d for c in self.scope if c["staff"] not in flagged and c["staff"] != self.twin
                 for d in self.by_staff[c["staff"]] if d["kind"] == "FDP" and not d["away"] and not d.get("tags")
                 and d["ref"] not in self.used and d["ref"] not in shown and d["report"] >= ftl.AMENDMENT_UTC + 36 * 60
                 and ftl.local_day(d["report"]) <= "2026-09-26"]
        rng.shuffle(cands)
        for d in cands:
            margin = _limit(d) - (ftl.duty_minutes(_as_duty(d, late=False)) - ftl.POST_FLIGHT)
            if not 60 <= margin <= 240:
                continue
            target = rng.randint(20, 45)
            d["late_shift"] = margin + target
            new = audit() - base
            if len(new) == 1:
                d["late_shift"] += target - next(iter(new))[1]
                new = audit() - base
            if len(new) == 1 and next(iter(new))[1] == target and next(iter(new))[0][1] == d["ref"] and next(iter(new))[0][2] == "FDP":
                self.used.add(d["ref"])
                self.tag(d, "late")
                self.triggers["c"] = {"duty": d["ref"], "staff": d["staff"], "on_blocks_before": to_iso(_end(d)),
                                      "on_blocks_after": to_iso(_end(d) + d["late_shift"]), "after_creates": 20}
                self.late_c_staff = d["staff"]
                return
            del d["late_shift"]
        raise RuntimeError("no duty can carry trigger c")

    def late_d(self):
        """Trigger d: a commander's discretion report sits unsigned in the reports database until the block is closed a
        second time, when it is signed. Before the signature the duty is an FDP finding at full excess; after it the
        extension stands and the same duty is a DISCRETION finding with a smaller excess, so the record must be restated."""
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        rng.random()
        rng.random()
        from . import emit
        all_duties = [d for ds in self.by_staff.values() for d in ds]
        scope_staff = {c["staff"] for c in self.scope}
        manifest = emit.media_manifest({"duties": all_duties, "evidence": self.evidence, "crew": self.crew, "voice_notes": self.notes})
        shown = {e["duty"] for kind in ("techlog", "scans") for e in manifest[kind]}

        def audit(late):
            return {(f.key, f.excess_min) for f in ftl.audit([_as_duty(d, late=late) for d in all_duties if d["staff"] in scope_staff])}

        base, base_pre = audit(True), audit(False)
        flagged = {k[0] for k, _ in base}
        cands = [d for c in self.scope if c["staff"] not in flagged and c["staff"] not in (self.twin, self.late_c_staff)
                 for d in self.by_staff[c["staff"]] if d["kind"] == "FDP" and not d["away"] and not d.get("tags")
                 and d["ref"] not in self.used and d["ref"] not in shown and d["report"] >= ftl.AMENDMENT_UTC + 36 * 60
                 and ftl.local_day(d["report"]) <= "2026-09-25"]
        rng.shuffle(cands)
        for d in cands:
            legs_on = d["legs"][-1]["on"]
            x = rng.randint(20, 45)
            _stretch(d, _limit(d) + ftl.DISCRETION_MAX["Rev 14"] + x)
            sid = f"CDR-{rng.randint(1000, 9999)}"
            d["late_report"] = sid
            pre, post = audit(False) - base_pre, audit(True) - base
            ok = (len(pre) == 1 and next(iter(pre))[0] == (d["staff"], d["ref"], "FDP") and next(iter(pre))[1] == ftl.DISCRETION_MAX["Rev 14"] + x
                  and len(post) == 1 and next(iter(post))[0] == (d["staff"], d["ref"], "DISCRETION") and next(iter(post))[1] == x
                  and base <= audit(True) and base_pre <= audit(False))
            if ok:
                self.used.add(d["ref"])
                self.tag(d, "late")
                d["evidence"] = (sid,)
                self.triggers["d"] = {"duty": d["ref"], "staff": d["staff"], "report_id": sid, "on_close": 2,
                                      "report": to_iso(d["report"]), "extension_end": to_iso(_end(d))}
                self.late_d_staff = d["staff"]
                return
            d["legs"][-1]["on"] = legs_on
            del d["late_report"]
        raise RuntimeError("no duty can carry trigger d")

    def ambience_late(self):
        """A second standby the ops record books at home but a call-log entry shows was served at the airport. Counted in
        full it takes an otherwise clear pilot's rolling 7-day duty over 60 hours; counted as home standby it does not."""
        import copy
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        for _ in range(3):
            rng.random()
        scope_staff = {c["staff"] for c in self.scope}

        def audit():
            return {(f.key, f.excess_min) for f in ftl.audit([_as_duty(d) for ds in self.by_staff.values() for d in ds if d["staff"] in scope_staff])}

        base = audit()
        flagged = {k[0] for k, _ in base}
        people = [c for c in self.scope if c["staff"] not in flagged and c["staff"] not in (self.twin, self.late_c_staff, self.late_d_staff)]
        rng.shuffle(people)
        for p in people:
            for end_day in ("2026-09-12", "2026-09-13", "2026-09-26", "2026-09-27"):
                saved_ds, saved_used, saved_notes = copy.deepcopy(self.by_staff[p["staff"]]), set(self.used), list(self.notes)
                ds = self.by_staff[p["staff"]]
                first = to_iso(to_min(end_day + "T00:00Z") - 6 * 1440)[:10]
                free = sorted(set(DAYS) - {ftl.local_day(d["report"]) for d in ds})
                day = next((x for x in free if first <= x <= end_day), None)
                if day is None:
                    continue
                start = _local(day, 360)
                ref = f"E9-{day[5:7]}{day[8:10]}-ABZ-{rng.randint(100, 999)}"
                sb = {"ref": ref, "staff": p["staff"], "kind": "AIRPORT_SB", "report": start, "end": start + 600,
                      "actual": {"ops_kind_override": "HOME_SB"}, "tags": ("audio",)}
                ds.append(sb)
                ds.sort(key=lambda x: x["report"])
                vn = f"VN-{rng.randint(100, 999)}"
                while any(n["id"] == vn for n in self.notes):
                    vn = f"VN-{rng.randint(100, 999)}"
                sb["evidence"] = (vn,)
                target = 3600 + rng.randint(15, 120)
                need = target - self._total(p, end_day, 7)
                if need > 0:
                    self._pad_window(p, first, 7, need, "audio_pad")
                full = self._total(p, end_day, 7)
                new = audit() - base
                ok = (3600 < full <= 3600 + 600 - int(600 * ftl.HOME_STANDBY_SHARE) and base <= audit() and len(new) == 1
                      and next(iter(new))[0][0] == p["staff"] and next(iter(new))[0][2] == "DUTY_7D")
                if ok:
                    sb_home = dict(sb, kind="HOME_SB")
                    ds[ds.index(sb)] = sb_home
                    ok = not ({(f.key, f.excess_min) for f in ftl.audit([_as_duty(d) for x in self.by_staff.values() for d in x if d["staff"] in scope_staff])} - base)
                    ds[ds.index(sb_home)] = sb
                if ok:
                    self.notes.append({"id": vn, "kind": "ambience", "duty": ref, "staff": p["staff"], "call": to_iso(start + 30), "ambience": "terminal"})
                    self.ambience_late_staff = p["staff"]
                    return
                self.by_staff[p["staff"]][:] = saved_ds
                self.used, self.notes = saved_used, saved_notes
        raise RuntimeError("no pilot can carry the second airport standby")

    def _late_onblocks(self, skips, exclude, when):
        """One unphotographed duty whose on-blocks the duty actuals move later mid-run, adding exactly one FDP finding."""
        from . import emit
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        for _ in range(skips):
            rng.random()
        all_duties = [d for ds in self.by_staff.values() for d in ds]
        scope_staff = {c["staff"] for c in self.scope}
        manifest = emit.media_manifest({"duties": all_duties, "evidence": self.evidence, "crew": self.crew, "voice_notes": self.notes})
        shown = {e["duty"] for kind in ("techlog", "scans") for e in manifest[kind]}

        def audit():
            return {(f.key, f.excess_min) for f in ftl.audit([_as_duty(d) for d in all_duties if d["staff"] in scope_staff])}

        base = audit()
        flagged = {k[0] for k, _ in base}
        cands = [d for c in self.scope if c["staff"] not in flagged and c["staff"] not in exclude
                 for d in self.by_staff[c["staff"]] if d["kind"] == "FDP" and not d["away"] and not d.get("tags")
                 and d["ref"] not in self.used and d["ref"] not in shown and abs(d["report"] - ftl.AMENDMENT_UTC) > 36 * 60
                 and ftl.local_day(d["report"]) <= "2026-09-26"]
        rng.shuffle(cands)
        for d in cands:
            margin = _limit(d) - (ftl.duty_minutes(_as_duty(d, late=False)) - ftl.POST_FLIGHT)
            if not 60 <= margin <= 240:
                continue
            target = rng.randint(20, 45)
            d["late_shift"] = margin + target
            new = audit() - base
            if len(new) == 1:
                d["late_shift"] += target - next(iter(new))[1]
                new = audit() - base
            if len(new) == 1 and next(iter(new))[1] == target and next(iter(new))[0][1] == d["ref"] and next(iter(new))[0][2] == "FDP":
                self.used.add(d["ref"])
                self.tag(d, "late")
                return {"duty": d["ref"], "staff": d["staff"], "on_blocks_before": to_iso(_end(d)),
                        "on_blocks_after": to_iso(_end(d) + d["late_shift"]), **when}
            del d["late_shift"]
        raise RuntimeError("no duty can carry a late on-blocks change")

    def unsigned_report(self):
        """A duty over its Appendix A limit but inside the discretion allowance, flagged as discretion in the duty actuals
        with a report on file that the commander never signed: the extension does not stand, so it is an FDP finding."""
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        for _ in range(7):
            rng.random()
        all_duties = [d for ds in self.by_staff.values() for d in ds]
        scope_staff = {c["staff"] for c in self.scope}

        def audit():
            return {(f.key, f.excess_min) for f in ftl.audit([_as_duty(d) for d in all_duties if d["staff"] in scope_staff])}

        from . import emit
        manifest = emit.media_manifest({"duties": all_duties, "evidence": self.evidence, "crew": self.crew, "voice_notes": self.notes})
        shown = {e["duty"] for kind in ("techlog", "scans") for e in manifest[kind]}
        base = audit()
        flagged = {k[0] for k, _ in base}
        busy = {self.twin, self.late_c_staff, self.late_d_staff, self.ambience_late_staff, self.late_f_staff}
        cands = [d for c in self.scope if c["staff"] not in busy
                 for d in self.by_staff[c["staff"]] if d["kind"] == "FDP" and not d["away"] and not d.get("tags")
                 and d["ref"] not in self.used and d["ref"] not in shown and d["report"] >= ftl.AMENDMENT_UTC + 36 * 60]
        rng.shuffle(cands)
        for d in cands:
            on = d["legs"][-1]["on"]
            x = rng.randint(25, 70)
            _stretch(d, _limit(d) + x)
            new = audit() - base
            if len(new) == 1 and next(iter(new)) == ((d["staff"], d["ref"], "FDP"), x) and base <= audit():
                sid = f"CDR-{rng.randint(1000, 9999)}"
                d["actual"]["discretion_used"] = True
                d["actual"]["discretion_report"] = sid
                d["unsigned_report"] = sid
                self.used.add(d["ref"])
                self.tag(d, "no_report")
                self.triggers["unsigned"] = {"duty": d["ref"], "staff": d["staff"], "report_id": sid, "report": to_iso(d["report"]),
                                             "extension_end": to_iso(_end(d))}
                self.unsigned_staff = d["staff"]
                return
            d["legs"][-1]["on"] = on
        raise RuntimeError("no duty can carry the unsigned report")

    def finish(self, duties):
        self._repair()
        self.late_c()
        self.late_d()
        self.ambience_late()
        self.triggers["f"] = self._late_onblocks(5, {self.twin, self.late_c_staff, self.late_d_staff, self.ambience_late_staff}, {"on_close": 2})
        self.late_f_staff = self.triggers["f"]["staff"]
        self.unsigned_report()
        all_duties = [d for ds in self.by_staff.values() for d in ds]
        resolved_pre = [_as_duty(d, late=False) for d in all_duties]
        resolved_post = [_as_duty(d, late=True) for d in all_duties]
        scope_staff = {c["staff"] for c in self.scope}
        pre = [f for f in ftl.audit([d for d in resolved_pre if d.staff in scope_staff])]
        post = [f for f in ftl.audit([d for d in resolved_post if d.staff in scope_staff])]
        index = {d.ref: d for d in resolved_post}
        ftl.assign_partitions(post, index)
        pre_keys = {(f.key, f.excess_min) for f in pre}
        for f in post:
            if (f.key, f.excess_min) not in pre_keys:
                f.partition = "late"
        late_staff = {self.late_staff, self.late_c_staff, self.late_d_staff, self.ambience_late_staff, self.late_f_staff, self.unsigned_staff}
        contacts = [c for c in self.scope if c["staff"] in {f.staff for f in post} and c["staff"] not in late_staff]
        contact = contacts[0]
        second = contacts[len(contacts) // 2]
        self.triggers["e"] = {"staff": second["staff"], "email_before": second["email"],
                              "email_after": f"{second['given'][0].lower()}{second['family'].lower()}@crew.{DOMAIN}", "on_close": 1}
        self.triggers["b"] = {"staff": contact["staff"], "email_before": contact["email"],
                              "email_after": f"{contact['given'].lower()}.{contact['family'].lower()}.fh@{DOMAIN}", "after_creates": 12}
        return {
            "airline": AIRLINE, "domain": DOMAIN, "stations": STATIONS,
            "crew": self.crew, "duties": all_duties, "evidence": self.evidence, "voice_notes": self.notes,
            "triggers": self.triggers, "twin": self.twin, "scope_staff": sorted(scope_staff), "ambience_late_staff": self.ambience_late_staff,
            "findings": [dict(asdict(f), key=list(f.key)) for f in post],
            "findings_before_trigger": [dict(asdict(f), key=list(f.key)) for f in pre],
        }


def _as_duty(d: dict, late: bool = True) -> Duty:
    if d["kind"] != "FDP":
        return Duty(d["ref"], d["staff"], d["kind"], d["report"], d["end"], evidence=tuple(d.get("evidence", ())),
                    tags=tuple(d.get("tags", ())))
    end = d["legs"][-1]["on"] + (d.get("late_shift", 0) if late else 0)
    return Duty(d["ref"], d["staff"], "FDP", d["report"], end, sectors=len(d["legs"]), positioning=d.get("positioning", False),
                away=d.get("away", False), discretion_filed=(bool(d.get("actual", {}).get("discretion_report", "").startswith("CDR"))
                                                 and not d.get("unsigned_report"))
                or (late and bool(d.get("late_report"))),
                evidence=tuple(d.get("evidence", ())), tags=tuple(d.get("tags", ())))
