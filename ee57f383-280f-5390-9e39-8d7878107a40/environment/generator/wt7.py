from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

PERIOD_START = datetime(2026, 10, 12, tzinfo=timezone.utc)
PERIOD_DAYS = 28
EDITION4_FIRST_DAY = 14
BST_END_UTC = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)

OPERATOR = "Brantlow Distribution Ltd"
DEPOT = "Keldford Regional Depot"
SISTER_DEPOT = "Marlbrook Satellite Depot"

DAILY_DRIVING_LIMIT = 540
CONTINUOUS_DRIVING_LIMIT = 270
BREAK_REQUIRED = 45
DAILY_REST_LIMIT = 660
WEEKLY_REST_LIMIT = 2700
DAILY_WORK_LIMIT = 660

EDITIONS = {
    3: {
        "label": "WT-7 Ed 3",
        "name": "Working Time and Drivers Hours Code WT-7, Edition 3",
        "night_from": 0,
        "night_to": 240,
        "night_work_limit": 480,
        "min_break_segment": 15,
        "poa_is_working_time": False,
        "weekly_basis": "fixed-calendar-week",
        "weekly_limit": 3600,
    },
    4: {
        "label": "WT-7 Ed 4",
        "name": "Working Time and Drivers Hours Code WT-7, Edition 4",
        "night_from": 1380,
        "night_to": 300,
        "night_work_limit": 420,
        "min_break_segment": 30,
        "poa_is_working_time": True,
        "weekly_basis": "rolling-7-day-reference-period",
        "weekly_limit": 3360,
    },
}

FINDING_TYPES = (
    "DAILY_DRIVING",
    "CONTINUOUS_DRIVING",
    "BREAK_COMPOSITION",
    "DAILY_REST",
    "WEEKLY_REST",
    "NIGHT_WORK",
    "AVAILABILITY",
    "ROLLING_WORKING_TIME",
)

SHORTFALL_TYPES = ("BREAK_COMPOSITION", "DAILY_REST", "WEEKLY_REST")

SURNAMES = (
    "Ashbourne", "Beddingfield", "Carvell", "Dunwoody", "Easterbrook", "Fennimore",
    "Gatacre", "Halliwell", "Inchbald", "Jerrold", "Kesterton", "Lanyon",
    "Mawdsley", "Netherwood", "Ollerenshaw", "Pennington", "Quarrell", "Rowntree",
    "Scarisbrick", "Thurlow", "Upcott", "Vardy", "Wakelin", "Yearsley",
    "Allardyce", "Birkenshaw", "Crowhurst", "Delamere", "Everingham", "Fotherby",
    "Grindrod", "Hollinrake", "Ibbotson", "Jolliffe", "Kingsnorth", "Loveridge",
    "Mottershead", "Nuttgens", "Oldacre", "Prestwich", "Rimmington", "Standen",
)
FORENAMES = (
    "Alun", "Bryher", "Caradoc", "Dilys", "Eifion", "Ffion", "Gethin", "Haf",
    "Idris", "Jowan", "Kerensa", "Llewelyn", "Mabyn", "Nerys", "Osian", "Petroc",
    "Rhodri", "Sulwen", "Tegan", "Urien", "Wyn", "Ynyr", "Aneira", "Bleddyn",
    "Cadell", "Delwyn", "Eurig", "Gwenda", "Heulwen", "Iestyn", "Lowri", "Meirion",
    "Nia", "Ofydd", "Pryderi", "Rhiannon", "Seiriol", "Tudur", "Wenna", "Alwena",
    "Brynmor", "Carys",
)
OPERATOR_MAIL_DOMAIN = "brantlow-distribution.co.uk"
AGENCY_MAIL_DOMAIN = "harrowgate-relief.co.uk"


def mail_address(forename: str, surname: str, domain: str) -> str:
    """Live register ContactAddress form; the compliance mailbox send tool consumes it."""
    return "%s.%s@%s" % (forename.lower(), surname.lower(), domain)


def reissued_mail_address(forename: str, surname: str, domain: str) -> str:
    """Second in-world mailbox form, so a superseded value differs as a string."""
    return "%s.%s@%s" % (forename[:1].lower(), surname.lower(), domain)


def day_date(day: int) -> datetime:
    return PERIOD_START + timedelta(days=day)


def offset_minutes(utc: datetime) -> int:
    return 60 if utc < BST_END_UTC else 0


def local_label(utc: datetime, *, forced_offset: int | None = None) -> str:
    off = offset_minutes(utc) if forced_offset is None else forced_offset
    shown = utc + timedelta(minutes=off)
    sign = "+" if off >= 0 else "-"
    return "%s%s%02d:%02d" % (shown.strftime("%Y-%m-%dT%H:%M:%S"), sign, abs(off) // 60, abs(off) % 60)


def utc_label(utc: datetime) -> str:
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_minute_of_day(utc: datetime) -> int:
    shown = utc + timedelta(minutes=offset_minutes(utc))
    return shown.hour * 60 + shown.minute


def duty_start_utc(day: int, local_hhmm: int) -> datetime:
    naive = day_date(day) + timedelta(minutes=local_hhmm)
    probe = naive - timedelta(minutes=60)
    off = offset_minutes(probe)
    return naive - timedelta(minutes=off)


def edition_for(utc_start: datetime) -> int:
    shown = utc_start + timedelta(minutes=offset_minutes(utc_start))
    return 4 if shown >= datetime(2026, 10, 26, tzinfo=timezone.utc) else 3


def spans_clock_change(start: datetime, end: datetime) -> bool:
    return start < BST_END_UTC < end


def break_segments_minutes(pattern: str) -> list:
    return [int(x) for x in pattern.split("+")]


def qualifying_break(pattern: str, edition: int) -> int:
    floor = EDITIONS[edition]["min_break_segment"]
    return sum(s for s in break_segments_minutes(pattern) if s >= floor)


def working_minutes(duty: dict, edition: int) -> int:
    total = duty["drive_min"] + duty["other_work_min"]
    if EDITIONS[edition]["poa_is_working_time"]:
        total += duty["poa_min"]
    return total


def touches_night_window(duty: dict, edition: int) -> bool:
    ed = EDITIONS[edition]
    start = local_minute_of_day(duty["start_utc"])
    span = duty["true_duration_min"]
    for offset in range(0, span + 1, 15):
        minute = (start + offset) % 1440
        if ed["night_from"] <= ed["night_to"]:
            if ed["night_from"] <= minute < ed["night_to"]:
                return True
        elif minute >= ed["night_from"] or minute < ed["night_to"]:
            return True
    return False


def _driver_id(index: int) -> str:
    return "BD-DRV-%04d" % (1300 + index * 7)


def _card_number(index: int) -> str:
    return "UK%07dK%03d" % (4180000 + index * 1237, 100 + index)


def _vehicle_reg(index: int) -> str:
    letters = "BCDFGHJKLMNPRSTVWXYZ"
    return "%s%s%02d %s%s%s" % (
        letters[index % 20], letters[(index * 3 + 5) % 20], 70 + (index % 5),
        letters[(index * 7 + 2) % 20], letters[(index * 11 + 9) % 20], letters[(index * 13 + 4) % 20],
    )


def build_people() -> dict:
    employed, agency, decoys = [], [], []
    for i in range(42):
        forename, surname = FORENAMES[i], SURNAMES[i]
        employed.append({
            "driver_id": _driver_id(i),
            "name": "%s %s" % (forename, surname),
            "card": _card_number(i),
            "address": mail_address(forename, surname, OPERATOR_MAIL_DOMAIN),
            "scope": "in-scope",
            "depot": DEPOT,
        })
    for i in range(8):
        forename, surname = FORENAMES[(i * 5 + 3) % 42], SURNAMES[(i * 9 + 24) % 42]
        agency.append({
            "driver_id": "BD-AGY-%04d" % (2400 + i * 13),
            "name": "%s %s" % (forename, surname),
            "card": "UK%07dA%03d" % (4390000 + i * 971, 300 + i),
            "address": mail_address(forename, surname, AGENCY_MAIL_DOMAIN),
            "scope": "agency",
            "depot": DEPOT,
        })
    decoy_specs = (
        (14, "Ollerenshaw"), (2, "Carvell"), (29, "Everingham"),
    )
    for n, (src, surname) in enumerate(decoy_specs):
        forename = FORENAMES[(src + 21) % 42]
        decoys.append({
            "driver_id": "BD-DRV-%04d" % (1301 + src * 7),
            "name": "%s %s" % (forename, surname),
            "card": "UK%07dM%03d" % (4180000 + src * 1237 + 4, 700 + n),
            "address": mail_address(forename, surname, OPERATOR_MAIL_DOMAIN),
            "scope": "out-of-scope-sister-depot",
            "depot": SISTER_DEPOT,
        })
    return {"employed": employed, "agency": agency, "decoys": decoys}


BASE_DAY = {
    "drive_min": 390, "other_work_min": 80, "poa_min": 25, "break_pattern": "45",
    "longest_continuous_min": 210, "daily_rest_before_min": 720,
    "local_start": 6 * 60, "true_duration_min": 540, "shape": "day-trunk",
}
BASE_LEG_A = {
    "drive_min": 190, "other_work_min": 40, "poa_min": 12, "break_pattern": "45",
    "longest_continuous_min": 190, "daily_rest_before_min": 720,
    "local_start": 6 * 60, "true_duration_min": 285, "shape": "multi-drop-leg-1",
}
BASE_LEG_B = {
    "drive_min": 200, "other_work_min": 40, "poa_min": 13, "break_pattern": "45",
    "longest_continuous_min": 200, "daily_rest_before_min": 0,
    "local_start": 15 * 60, "true_duration_min": 300, "shape": "multi-drop-leg-2",
}
BASE_NIGHT = {
    "drive_min": 300, "other_work_min": 60, "poa_min": 40, "break_pattern": "45",
    "longest_continuous_min": 260, "daily_rest_before_min": 780,
    "local_start": 21 * 60 + 30, "true_duration_min": 420, "shape": "night-trunk",
}

CLOCK_CHANGE_NIGHT_DAY = 12
CLOCK_CHANGE_DRIVERS = (3, 4, 5, 6, 7, 8)
NIGHT_FINDING_DUTIES = {(5, 20): "e3", (9, 25): "e3", (18, 28): "e4", (22, 33): "e4"}
FIXED_OFFSET_CONTROL = (16, 11)
VEHICLE_UNIT_KEYED_EARLY_DRIVER = 3
ROSTER_OVERSTATED_DRIVER = 8


def night_map() -> dict:
    out = {}
    for i in CLOCK_CHANGE_DRIVERS:
        out[(CLOCK_CHANGE_NIGHT_DAY, i)] = "clock-change"
    for key in NIGHT_FINDING_DUTIES:
        out[key] = "night-finding"
    out[FIXED_OFFSET_CONTROL] = "fixed-offset-control"
    return out


def _on_duty(driver_index: int, day: int) -> bool:
    return (day + driver_index) % 7 != 0


def build_duties(people: dict) -> list:
    duty_days = []
    for day in range(PERIOD_DAYS):
        for i in range(42):
            if _on_duty(i, day):
                duty_days.append((day, i))
    nights = night_map()
    splittable = [n for n, key in enumerate(duty_days) if (key[0], key[1]) not in nights]
    split_positions = set(splittable[:: max(1, len(splittable) // 172)][:172])

    duties = []
    seq = 0
    for position, (day, i) in enumerate(duty_days):
        driver = people["employed"][i]
        night_kind = nights.get((day, i))
        if night_kind:
            shapes = [BASE_NIGHT]
        elif position in split_positions:
            shapes = [BASE_LEG_A, BASE_LEG_B]
        else:
            shapes = [BASE_DAY]
        for leg, shape in enumerate(shapes):
            seq += 1
            start = duty_start_utc(day, shape["local_start"])
            duty = dict(shape)
            duty.update({
                "duty_ref": "KD-%s-%03d" % (day_date(day).strftime("%d%m"), 40 + leg * 400 + i * 9),
                "seq": seq,
                "day": day,
                "driver_index": i,
                "driver_id": driver["driver_id"],
                "vehicle": _vehicle_reg((i * 3 + day) % 30),
                "start_utc": start,
                "leg": leg,
                "rest_governed": leg == 0,
                "weekly_rest_before_min": 2880 if _is_week_open(i, day) and leg == 0 else 0,
                "unit_offset_habit": 60,
                "gap": False,
                "planted": [],
                "night_kind": night_kind,
            })
            duty["end_utc"] = start + timedelta(minutes=duty["true_duration_min"])
            duties.append(duty)
    return duties


def _is_week_open(driver_index: int, day: int) -> bool:
    return (day + driver_index) % 7 == 1


PLANTED_TABLE = (
    ("DAILY_DRIVING", 0, 0, {"drive_min": 585, "other_work_min": 60, "poa_min": 10, "longest_continuous_min": 255}),
    ("DAILY_DRIVING", 3, 0, {"drive_min": 612, "other_work_min": 40, "poa_min": 8, "longest_continuous_min": 265}),
    ("DAILY_DRIVING", 6, 0, {"drive_min": 560, "other_work_min": 55, "poa_min": 15, "longest_continuous_min": 240}),
    ("DAILY_DRIVING", 8, 0, {"drive_min": 598, "other_work_min": 45, "poa_min": 12, "longest_continuous_min": 250}),
    ("DAILY_DRIVING", 11, 0, {"drive_min": 571, "other_work_min": 60, "poa_min": 20, "longest_continuous_min": 245}),
    ("DAILY_DRIVING", 16, 14, {"drive_min": 604, "other_work_min": 40, "poa_min": 10, "longest_continuous_min": 262}),
    ("DAILY_DRIVING", 18, 14, {"drive_min": 556, "other_work_min": 65, "poa_min": 18, "longest_continuous_min": 238}),
    ("DAILY_DRIVING", 21, 14, {"drive_min": 627, "other_work_min": 25, "poa_min": 6, "longest_continuous_min": 268}),
    ("DAILY_DRIVING", 25, 14, {"drive_min": 568, "other_work_min": 60, "poa_min": 14, "longest_continuous_min": 242}),
    ("DAILY_DRIVING", 27, 14, {"drive_min": 592, "other_work_min": 50, "poa_min": 11, "longest_continuous_min": 258}),
    ("CONTINUOUS_DRIVING", 1, 0, {"longest_continuous_min": 318}),
    ("CONTINUOUS_DRIVING", 5, 0, {"longest_continuous_min": 295}),
    ("CONTINUOUS_DRIVING", 15, 0, {"longest_continuous_min": 342}),
    ("CONTINUOUS_DRIVING", 20, 14, {"longest_continuous_min": 289}),
    ("CONTINUOUS_DRIVING", 26, 14, {"longest_continuous_min": 327}),
    ("BREAK_COMPOSITION", 2, 14, {"break_pattern": "15+30"}),
    ("BREAK_COMPOSITION", 9, 14, {"break_pattern": "20+25"}),
    ("BREAK_COMPOSITION", 22, 14, {"break_pattern": "15+30"}),
    ("BREAK_COMPOSITION", 24, 14, {"break_pattern": "20+25"}),
    ("DAILY_REST", 4, 0, {"daily_rest_before_min": 585}),
    ("DAILY_REST", 7, 0, {"daily_rest_before_min": 540}),
    ("DAILY_REST", 12, 0, {"daily_rest_before_min": 612}),
    ("DAILY_REST", 19, 14, {"daily_rest_before_min": 498}),
    ("DAILY_REST", 23, 14, {"daily_rest_before_min": 627}),
    ("WEEKLY_REST", 10, 0, {"weekly_rest_before_min": 2520}),
    ("WEEKLY_REST", 17, 14, {"weekly_rest_before_min": 2385}),
    ("AVAILABILITY", 14, 14, {"drive_min": 420, "other_work_min": 150, "poa_min": 120, "longest_continuous_min": 205}),
    ("AVAILABILITY", 29, 14, {"drive_min": 410, "other_work_min": 160, "poa_min": 135, "longest_continuous_min": 200}),
    ("AVAILABILITY", 31, 14, {"drive_min": 430, "other_work_min": 145, "poa_min": 110, "longest_continuous_min": 210}),
)

NIGHT_PLANTED = {
    (5, 20): {"drive_min": 330, "other_work_min": 170, "poa_min": 40, "longest_continuous_min": 262},
    (9, 25): {"drive_min": 320, "other_work_min": 185, "poa_min": 35, "longest_continuous_min": 258},
    (18, 28): {"drive_min": 300, "other_work_min": 95, "poa_min": 55, "longest_continuous_min": 250},
    (22, 33): {"drive_min": 310, "other_work_min": 90, "poa_min": 60, "longest_continuous_min": 255},
}

CLOCK_CHANGE_PLANTED = {
    3: {"drive_min": 561, "other_work_min": 55, "poa_min": 18, "longest_continuous_min": 248,
        "true_duration_min": 690, "local_start": 21 * 60},
    4: {"drive_min": 400, "other_work_min": 80, "poa_min": 30, "longest_continuous_min": 301,
        "true_duration_min": 690, "local_start": 21 * 60},
    5: {"break_pattern": "10+35", "true_duration_min": 690, "local_start": 21 * 60},
}

ROLLING_PLANTED = ((30, 14, 70), (37, 20, 85))

CERTIFICATE_GOVERNED_PLANTS = (("DAILY_DRIVING", 0), ("DAILY_REST", 7), ("DAILY_DRIVING", 25))
CONTRADICTING_CARRIER_PLANTS = (("DAILY_DRIVING", 3), ("CONTINUOUS_DRIVING", 15), ("DAILY_DRIVING", 21))


def apply_plants(duties: list) -> None:
    by_driver_day = {}
    for duty in duties:
        by_driver_day.setdefault((duty["driver_index"], duty["day"]), []).append(duty)

    def first_leg(driver_index, day):
        legs = by_driver_day.get((driver_index, day))
        return legs[0] if legs else None

    chosen = {}
    for ftype, driver_index, min_day, overrides in PLANTED_TABLE:
        for day in range(min_day, PERIOD_DAYS):
            duty = first_leg(driver_index, day)
            if duty is None or duty["planted"] or duty["night_kind"]:
                continue
            if len(by_driver_day[(driver_index, day)]) > 1:
                continue
            if ftype == "WEEKLY_REST" and duty["weekly_rest_before_min"] == 0:
                continue
            if ftype != "WEEKLY_REST" and duty["weekly_rest_before_min"]:
                continue
            duty.update(overrides)
            duty["planted"].append(ftype)
            duty["end_utc"] = duty["start_utc"] + timedelta(minutes=duty["true_duration_min"])
            chosen[(ftype, driver_index)] = duty
            break

    for (day, driver_index), overrides in sorted(NIGHT_PLANTED.items()):
        duty = first_leg(driver_index, day)
        duty.update(overrides)
        duty["planted"].append("NIGHT_WORK")
        duty["end_utc"] = duty["start_utc"] + timedelta(minutes=duty["true_duration_min"])

    for driver_index in sorted(CLOCK_CHANGE_PLANTED):
        duty = first_leg(driver_index, CLOCK_CHANGE_NIGHT_DAY)
        duty.update(CLOCK_CHANGE_PLANTED[driver_index])
        duty["start_utc"] = duty_start_utc(CLOCK_CHANGE_NIGHT_DAY, duty["local_start"])
        duty["end_utc"] = duty["start_utc"] + timedelta(minutes=duty["true_duration_min"])

    for duty in duties:
        if duty["night_kind"] == "clock-change":
            duty["clock_change_partition"] = True
            duty["spans_change"] = spans_clock_change(duty["start_utc"], duty["end_utc"])
        if duty["night_kind"] == "fixed-offset-control":
            duty["fixed_offset_control"] = True
        if duty["driver_index"] == VEHICLE_UNIT_KEYED_EARLY_DRIVER and duty["night_kind"] == "clock-change":
            duty["unit_keyed_early"] = True
        if duty["driver_index"] == ROSTER_OVERSTATED_DRIVER and duty["night_kind"] == "clock-change":
            duty["roster_overstated"] = True

    for driver_index, anchor, bump in ROLLING_PLANTED:
        for offset in range(7):
            leg = first_leg(driver_index, anchor + offset)
            if leg is not None:
                leg["other_work_min"] += bump
                leg["rolling_bumped"] = True

    for key in CERTIFICATE_GOVERNED_PLANTS:
        duty = chosen.get(key)
        if duty is not None:
            duty["gap"] = True
            duty["certificate_governed"] = True
    for key in CONTRADICTING_CARRIER_PLANTS:
        duty = chosen.get(key)
        if duty is not None:
            duty["contradicting_carrier"] = True


def find_duty_exceedances(duty: dict) -> list:
    edition = edition_for(duty["start_utc"])
    ed = EDITIONS[edition]
    out = []
    if duty["drive_min"] > DAILY_DRIVING_LIMIT:
        out.append(("DAILY_DRIVING", DAILY_DRIVING_LIMIT, duty["drive_min"],
                    duty["drive_min"] - DAILY_DRIVING_LIMIT))
    if duty["longest_continuous_min"] > CONTINUOUS_DRIVING_LIMIT:
        out.append(("CONTINUOUS_DRIVING", CONTINUOUS_DRIVING_LIMIT, duty["longest_continuous_min"],
                    duty["longest_continuous_min"] - CONTINUOUS_DRIVING_LIMIT))
    qualifying = qualifying_break(duty["break_pattern"], edition)
    if qualifying < BREAK_REQUIRED:
        out.append(("BREAK_COMPOSITION", BREAK_REQUIRED, qualifying, BREAK_REQUIRED - qualifying))
    if duty["rest_governed"] and duty["daily_rest_before_min"] < DAILY_REST_LIMIT:
        out.append(("DAILY_REST", DAILY_REST_LIMIT, duty["daily_rest_before_min"],
                    DAILY_REST_LIMIT - duty["daily_rest_before_min"]))
    if duty["weekly_rest_before_min"] and duty["weekly_rest_before_min"] < WEEKLY_REST_LIMIT:
        out.append(("WEEKLY_REST", WEEKLY_REST_LIMIT, duty["weekly_rest_before_min"],
                    WEEKLY_REST_LIMIT - duty["weekly_rest_before_min"]))
    work = working_minutes(duty, edition)
    if touches_night_window(duty, edition) and work > ed["night_work_limit"]:
        out.append(("NIGHT_WORK", ed["night_work_limit"], work, work - ed["night_work_limit"]))
    if work > DAILY_WORK_LIMIT:
        out.append(("AVAILABILITY", DAILY_WORK_LIMIT, work, work - DAILY_WORK_LIMIT))
    return [(t, lim, act, exc) for (t, lim, act, exc) in out if exc > 0]


def find_weekly_exceedances(duties: list) -> list:
    by_driver = {}
    for duty in duties:
        by_driver.setdefault(duty["driver_index"], []).append(duty)
    out = []
    for driver_index in sorted(by_driver):
        rows = sorted(by_driver[driver_index], key=lambda d: (d["start_utc"], d["duty_ref"]))
        for week in range(4):
            days = range(week * 7, week * 7 + 7)
            member = [d for d in rows if d["day"] in days and edition_for(d["start_utc"]) == 3]
            if member:
                total = sum(working_minutes(d, 3) for d in member)
                if total > EDITIONS[3]["weekly_limit"]:
                    out.append((member[-1], "ROLLING_WORKING_TIME", 3, EDITIONS[3]["weekly_limit"],
                                total, total - EDITIONS[3]["weekly_limit"]))
        for anchor in range(EDITION4_FIRST_DAY, PERIOD_DAYS):
            window = range(anchor - 6, anchor + 1)
            member = [d for d in rows if d["day"] in window and edition_for(d["start_utc"]) == 4]
            if not member:
                continue
            total = sum(working_minutes(d, 4) for d in member)
            if total > EDITIONS[4]["weekly_limit"]:
                out.append((member[-1], "ROLLING_WORKING_TIME", 4, EDITIONS[4]["weekly_limit"],
                            total, total - EDITIONS[4]["weekly_limit"]))
                break
    return out


def partition_of(duty: dict, ftype: str) -> str:
    if duty.get("clock_change_partition"):
        return "clock-change"
    if duty.get("certificate_governed"):
        return "override"
    if duty.get("contradicting_carrier"):
        return "contradiction"
    if ftype == "NIGHT_WORK":
        return "night-work"
    if ftype in ("BREAK_COMPOSITION", "AVAILABILITY", "ROLLING_WORKING_TIME"):
        return "edition-split"
    if ftype in ("DAILY_REST", "WEEKLY_REST"):
        return "rest"
    return "core-daily-driving"


PARTITION_WEIGHT = {
    "core-daily-driving": 1, "rest": 3, "edition-split": 5, "override": 5,
    "night-work": 5, "clock-change": 5, "contradiction": 5,
}


def reference_findings(duties: list) -> list:
    findings = []
    for duty in sorted(duties, key=lambda d: (d["start_utc"], d["duty_ref"])):
        if duty["gap"] and not duty.get("certificate_governed"):
            continue
        edition = edition_for(duty["start_utc"])
        for ftype, limit, actual, excess in find_duty_exceedances(duty):
            findings.append({
                "driver_id": duty["driver_id"],
                "duty_ref": duty["duty_ref"],
                "finding_type": ftype,
                "edition": EDITIONS[edition]["label"],
                "limit_minutes": limit,
                "actual_minutes": actual,
                "excess_minutes": excess,
                "partition": partition_of(duty, ftype),
                "basis": "shortfall" if ftype in SHORTFALL_TYPES else "excess",
            })
    for duty, ftype, edition, limit, actual, excess in find_weekly_exceedances(duties):
        findings.append({
            "driver_id": duty["driver_id"],
            "duty_ref": duty["duty_ref"],
            "finding_type": ftype,
            "edition": EDITIONS[edition]["label"],
            "limit_minutes": limit,
            "actual_minutes": actual,
            "excess_minutes": excess,
            "partition": "edition-split",
            "basis": "excess",
        })
    findings.sort(key=lambda f: (f["duty_ref"], f["finding_type"]))
    return findings


def world_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
