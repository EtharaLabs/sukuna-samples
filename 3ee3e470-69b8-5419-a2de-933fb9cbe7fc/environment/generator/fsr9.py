from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

PERIOD_START = datetime(2026, 10, 5, tzinfo=timezone.utc)
PERIOD_DAYS = 28
REVISION_C_FIRST_DAY = 14
SUMMER_END_UTC = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
REVISION_C_LOCAL_START = datetime(2026, 10, 19, tzinfo=timezone.utc)

OPERATOR = "Thornby Field Services Ltd"
HUB = "Calderwick Regional Network Operations"
SISTER_REGION = "Pellworth Coastal Region"
STANDARD = "Field Service Response Code FSR-9"

RESPONSE_TARGET = 120
ACK_TARGET = 20
TRAVEL_CAP_C = 60
TRAVEL_FIXED_B = 45
REMOTE_WINDOW_C = 15
PARTS_WAIT_FLOOR_B = 30

REVISIONS = {
    "B": {
        "label": "FSR-9 Rev B",
        "name": "Field Service Response Code FSR-9, Revision B",
        "clock_start": "dispatch",
        "travel_basis": "fixed-allowance",
        "travel_fixed_minutes": TRAVEL_FIXED_B,
        "travel_cap_minutes": 0,
        "parts_wait_suspends": False,
        "remote_counts_as_response": False,
        "remote_window_minutes": 0,
    },
    "C": {
        "label": "FSR-9 Rev C",
        "name": "Field Service Response Code FSR-9, Revision C",
        "clock_start": "acknowledgement",
        "travel_basis": "telemetry-recorded-capped",
        "travel_fixed_minutes": 0,
        "travel_cap_minutes": TRAVEL_CAP_C,
        "parts_wait_suspends": True,
        "remote_counts_as_response": True,
        "remote_window_minutes": REMOTE_WINDOW_C,
    },
}

FINDING_TYPES = (
    "RESPONSE_TARGET",
    "ACKNOWLEDGEMENT_DELAY",
    "TRAVEL_CAP_BREACH",
    "PARTS_WAIT_UNSUSPENDED",
    "REMOTE_ATTEMPT_LATE",
    "CERTIFICATE_OVERRIDE",
    "BADGE_OFFSET_MISMATCH",
    "TELEMETRY_TOTAL_MISMATCH",
    "HANDBACK_DOCUMENT_CONFLICT",
)

SURNAMES = (
    "Wraysbury", "Molyneaux", "Tredinnick", "Hasselgrove", "Pentreath", "Garmondsway",
    "Linnersgill", "Quennell", "Arrowsmith-Vale", "Shackwell", "Oxenhope", "Dunnamore",
    "Trevellick", "Birkitt", "Lonsborough", "Harrowden", "Needingworth", "Caulderbank",
    "Ravensmoor",
)
FORENAMES = (
    "Marek", "Oriel", "Teagan", "Dov", "Ingrid", "Samira", "Lucan", "Ffyona",
    "Beren", "Niamh", "Cosmo", "Elspeth", "Rafferty", "Juno", "Hollis", "Verity",
    "Casimir", "Thandiwe", "Emrys",
)

OPERATOR_MAIL_DOMAIN = "thornby-field.co.uk"
CONTRACTOR_MAIL_DOMAIN = "westmarch-engineering.co.uk"

EMPLOYED_COUNT = 12
CONTRACTOR_COUNT = 4
DECOY_COUNT = 3

SITE_CODES = (
    "CWK-NORTHGATE", "CWK-BRINDLE-ROW", "CWK-SALTMARSH", "CWK-HOLLOWAY-RISE",
    "CWK-TANNERS-END", "CWK-FIVE-OAKS", "CWK-WESTERLY-SPUR", "CWK-LOWER-MERE",
    "CWK-ABBOTS-FORD", "CWK-GRENVILLE-WAY", "CWK-STOURBANK", "CWK-NINE-ELMS",
)
SEVERITIES = ("priority-one", "priority-two", "priority-three")


def mail_address(forename: str, surname: str, domain: str) -> str:
    """Live register MailAddress form; the operations mailbox send tool consumes it."""
    return "%s.%s@%s" % (forename.lower(), surname.lower().replace("-", ""), domain)


def amended_mail_address(forename: str, surname: str, domain: str) -> str:
    """Second in-world mailbox form, so a superseded value differs as a string."""
    return "%s%s@%s" % (forename[:1].lower(), surname.lower().replace("-", ""), domain)


def day_date(day: int) -> datetime:
    return PERIOD_START + timedelta(days=day)


def offset_minutes(utc: datetime) -> int:
    """Depot local offset as pure arithmetic. No zoneinfo, no locale."""
    return 60 if utc < SUMMER_END_UTC else 0


def local_label(utc: datetime, *, forced_offset=None) -> str:
    off = offset_minutes(utc) if forced_offset is None else forced_offset
    shown = utc + timedelta(minutes=off)
    sign = "+" if off >= 0 else "-"
    return "%s%s%02d:%02d" % (shown.strftime("%Y-%m-%dT%H:%M:%S"), sign,
                              abs(off) // 60, abs(off) % 60)


def utc_label(utc: datetime) -> str:
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_clock(utc: datetime, *, forced_offset=None) -> str:
    off = offset_minutes(utc) if forced_offset is None else forced_offset
    return (utc + timedelta(minutes=off)).strftime("%H:%M")


def local_minute_of_day(utc: datetime) -> int:
    shown = utc + timedelta(minutes=offset_minutes(utc))
    return shown.hour * 60 + shown.minute


def instant_from_local(day: int, local_hhmm: int) -> datetime:
    """Build a UTC instant from a depot-local wall time on a period day."""
    naive = day_date(day) + timedelta(minutes=local_hhmm)
    probe = naive - timedelta(minutes=60)
    return naive - timedelta(minutes=offset_minutes(probe))


def revision_for(dispatch_utc: datetime) -> str:
    """The paging dispatch instant in depot local time decides the revision."""
    shown = dispatch_utc + timedelta(minutes=offset_minutes(dispatch_utc))
    return "C" if shown >= REVISION_C_LOCAL_START else "B"


def spans_clock_change(start: datetime, end: datetime) -> bool:
    return start < SUMMER_END_UTC < end


def effective_clear(inc: dict) -> datetime:
    """Signed hand-back documentation supersedes the auto-logged clear heartbeat."""
    return inc["clear_utc"] + timedelta(minutes=inc.get("handback_delta_min", 0))


def clock_start_instant(inc: dict, revision: str) -> datetime:
    if REVISIONS[revision]["clock_start"] == "acknowledgement":
        return inc["ack_utc"]
    return inc["dispatch_utc"]


def travel_allowance(inc: dict, revision: str) -> int:
    rev = REVISIONS[revision]
    if rev["travel_basis"] == "fixed-allowance":
        return rev["travel_fixed_minutes"]
    return min(inc["telemetry_travel_min"], rev["travel_cap_minutes"])


def allowance_minutes(inc: dict, revision: str) -> int:
    return RESPONSE_TARGET + travel_allowance(inc, revision)


def suspended_minutes(inc: dict, revision: str) -> int:
    if REVISIONS[revision]["parts_wait_suspends"]:
        return inc["parts_wait_min"]
    return 0


def remote_satisfies(inc: dict, revision: str) -> bool:
    rev = REVISIONS[revision]
    if not rev["remote_counts_as_response"]:
        return False
    first = inc.get("remote_attempt_min")
    if first is None:
        return False
    return first <= rev["remote_window_minutes"]


def actual_minutes(inc: dict, revision: str) -> int:
    if remote_satisfies(inc, revision):
        return inc["remote_attempt_min"]
    start = clock_start_instant(inc, revision)
    elapsed = int((effective_clear(inc) - start).total_seconds() // 60)
    return max(0, elapsed - suspended_minutes(inc, revision))


def ack_delay_minutes(inc: dict) -> int:
    return int((inc["ack_utc"] - inc["dispatch_utc"]).total_seconds() // 60)


def _incident_ref(day: int, n: int) -> str:
    return "CRN-%s-%03d" % (day_date(day).strftime("%d%m"), 110 + n * 7)


def _engineer_id(index: int) -> str:
    return "TFS-ENG-%03d" % (203 + index * 4)


def _contractor_id(index: int) -> str:
    return "TFS-CTR-%03d" % (641 + index * 6)


def _van_code(index: int) -> str:
    letters = "BCDFGHJKLMNPRSTVWXYZ"
    return "VAN-%s%s-%02d" % (letters[index % 20], letters[(index * 5 + 3) % 20],
                              40 + (index % 9))


def _radio_handle(index: int) -> str:
    return "CW%03dR" % (310 + index * 3)


def build_people() -> dict:
    employed, contractors, decoys = [], [], []
    for i in range(EMPLOYED_COUNT):
        forename, surname = FORENAMES[i], SURNAMES[i]
        employed.append({
            "engineer_id": _engineer_id(i),
            "name": "%s %s" % (forename, surname),
            "radio": _radio_handle(i),
            "van": _van_code(i),
            "address": mail_address(forename, surname, OPERATOR_MAIL_DOMAIN),
            "scope": "in-scope",
            "region": HUB,
            "grade": "field engineer",
        })
    for i in range(CONTRACTOR_COUNT):
        forename = FORENAMES[(i * 3 + 13) % len(FORENAMES)]
        surname = SURNAMES[(i * 5 + 12) % len(SURNAMES)]
        contractors.append({
            "engineer_id": _contractor_id(i),
            "name": "%s %s" % (forename, surname),
            "radio": "CW%03dA" % (480 + i * 4),
            "van": _van_code(20 + i),
            "address": mail_address(forename, surname, CONTRACTOR_MAIL_DOMAIN),
            "scope": "agency",
            "region": HUB,
            "grade": "supplied engineer",
        })
    for n, src in enumerate((2, 6, 10)):
        forename = FORENAMES[(src + 7) % len(FORENAMES)]
        surname = SURNAMES[src]
        decoys.append({
            "engineer_id": "TFS-ENG-%03d" % (203 + src * 4 + 1),
            "name": "%s %s" % (forename, surname),
            "radio": "PW%03dR" % (710 + n * 3),
            "van": _van_code(26 + n),
            "address": mail_address(forename, surname, OPERATOR_MAIL_DOMAIN),
            "scope": "out-of-region",
            "region": SISTER_REGION,
            "grade": "field engineer",
        })
    return {"employed": employed, "contractors": contractors, "decoys": decoys}


BASE_CALL = {
    "local_dispatch": 9 * 60 + 10,
    "ack_delay_min": 9,
    "travel_min": 38,
    "on_site_min": 54,
    "parts_wait_min": 0,
    "remote_attempt_min": None,
    "handback_delta_min": 0,
    "shape": "scheduled-window-call",
}
BASE_EVENING = {
    "local_dispatch": 18 * 60 + 40,
    "ack_delay_min": 12,
    "travel_min": 41,
    "on_site_min": 58,
    "parts_wait_min": 0,
    "remote_attempt_min": None,
    "handback_delta_min": 0,
    "shape": "evening-callout",
}
BASE_NIGHT = {
    "local_dispatch": 22 * 60 + 25,
    "ack_delay_min": 14,
    "travel_min": 44,
    "on_site_min": 61,
    "parts_wait_min": 0,
    "remote_attempt_min": None,
    "handback_delta_min": 0,
    "shape": "night-standby-callout",
}
SHAPE_CYCLE = (BASE_CALL, BASE_EVENING, BASE_NIGHT, BASE_CALL)

CALLS_PER_DAY = 3
EXTRA_CALL_DAYS = (2, 7, 11, 16, 20, 25)


def _engineer_for(day: int, n: int, people: dict) -> dict:
    """The on-call roster is the only carrier that resolves a dispatch to an identity."""
    slot = (day * CALLS_PER_DAY + n)
    if slot % 11 == 4:
        return people["contractors"][(slot // 11) % CONTRACTOR_COUNT]
    return people["employed"][slot % EMPLOYED_COUNT]


def build_incidents(people: dict) -> list:
    incidents = []
    seq = 0
    for day in range(PERIOD_DAYS):
        count = CALLS_PER_DAY + (1 if day in EXTRA_CALL_DAYS else 0)
        for n in range(count):
            shape = SHAPE_CYCLE[(day + n) % len(SHAPE_CYCLE)]
            engineer = _engineer_for(day, n, people)
            seq += 1
            inc = dict(shape)
            dispatch = instant_from_local(day, shape["local_dispatch"] + n * 23)
            inc.update({
                "incident_ref": _incident_ref(day, n),
                "seq": seq,
                "day": day,
                "slot": n,
                "engineer_id": engineer["engineer_id"],
                "engineer_scope": engineer["scope"],
                "site_code": SITE_CODES[(day * 5 + n * 3) % len(SITE_CODES)],
                "severity": SEVERITIES[(day + n) % len(SEVERITIES)],
                "van": engineer["van"],
                "dispatch_utc": dispatch,
                "planted": [],
                "telemetry_leg_count": 2 + (seq % 3),
            })
            inc["telemetry_travel_min"] = inc["travel_min"]
            _retime(inc)
            incidents.append(inc)
    return incidents


def _retime(inc: dict) -> None:
    inc["ack_utc"] = inc["dispatch_utc"] + timedelta(minutes=inc["ack_delay_min"])
    inc["arrival_utc"] = inc["ack_utc"] + timedelta(minutes=inc["travel_min"])
    inc["clear_utc"] = (inc["arrival_utc"] + timedelta(minutes=inc["on_site_min"])
                        + timedelta(minutes=inc["parts_wait_min"]))
    inc["revision"] = revision_for(inc["dispatch_utc"])
    inc["spans_change"] = spans_clock_change(inc["dispatch_utc"], inc["clear_utc"])


CORE_RESPONSE_PLANTS = (
    (0, 0, 22, {}),
    (1, 1, 35, {}),
    (3, 0, 18, {}),
    (5, 2, 47, {}),
    (8, 1, 29, {}),
    (23, 0, 26, {"travel_min": 52}),
    (26, 2, 41, {"travel_min": 49}),
)
ACK_DELAY_PLANTS = (
    (2, 1, 14, {"on_site_min": 40}),
    (12, 0, 21, {"on_site_min": 40}),
    (24, 2, 9, {"on_site_min": 40}),
)
TRAVEL_CAP_PLANTS = (
    (15, 0, 29, {"travel_min": 83}),
    (17, 2, 42, {"travel_min": 91}),
    (19, 1, 41, {"travel_min": 77}),
    (22, 0, 30, {"travel_min": 88, "parts_wait_min": 35}),
    (27, 1, 24, {"travel_min": 95}),
)
PARTS_WAIT_PLANTS = (
    (4, 2, 33, {"parts_wait_min": 64}),
    (6, 0, 51, {"parts_wait_min": 81}),
    (9, 1, 19, {"parts_wait_min": 57}),
    (11, 2, 38, {"parts_wait_min": 73}),
)
REMOTE_LATE_PLANTS = (
    (14, 1, 27, {"remote_attempt_min": 27}),
    (18, 0, 44, {"remote_attempt_min": 34}),
    (21, 2, 16, {"remote_attempt_min": 22}),
    (25, 1, 36, {"remote_attempt_min": 41}),
)
REVISION_SPLIT_PLANTS = (
    (13, 2, 23, {"local_dispatch": 23 * 60 + 35}),
    (14, 0, 31, {"local_dispatch": 0 * 60 + 25}),
    (14, 2, 17, {"local_dispatch": 23 * 60 + 50}),
    (15, 1, 45, {"local_dispatch": 1 * 60 + 15}),
    (16, 0, 28, {"local_dispatch": 23 * 60 + 40}),
    (20, 2, 39, {"local_dispatch": 0 * 60 + 45}),
)
CERTIFICATE_PLANTS = (
    (7, 1, 34, {}),
    (10, 0, 20, {}),
    (19, 2, 43, {}),
)
BADGE_EXPORT_PLANTS = (
    (6, 2, 25, {"travel_min": 47}),
    (21, 0, 37, {"travel_min": 51}),
)
TELEMETRY_PLANTS = (
    (24, 0, 32, {"travel_min": 74}),
    (24, 1, 15, {"travel_min": 69}),
)
CROSS_MODAL_PLANT = (16, 2, 24, {"handback_delta_min": 44})
HANDBACK_CONTROL_PLANT = (9, 0, {"on_site_min": 63, "handback_delta_min": 0})
NEGATIVE_CONTROL_PLANT = (12, 2, {"ack_delay_min": 18, "travel_min": 55,
                                  "on_site_min": 44, "parts_wait_min": 0})

CERTIFICATE_DECLARED_SHIFT = 26
TELEMETRY_UNDERSTATEMENT = 88
BADGE_EXPORT_OFFSET_TRAP = 60
PARTS_MOVE_DELTA = 25
REMOTE_MOVE_NEW = 11


def _find(incidents: list, day: int, slot: int) -> dict:
    for inc in incidents:
        if inc["day"] == day and inc["slot"] == slot:
            return inc
    raise KeyError("no dispatch record at day %d slot %d" % (day, slot))


def _reassign_to_employed(inc: dict, people: dict) -> None:
    """A planted exceedance is always owned by an employed engineer."""
    if inc["engineer_scope"] == "in-scope":
        return
    engineer = people["employed"][inc["seq"] % EMPLOYED_COUNT]
    inc["engineer_id"] = engineer["engineer_id"]
    inc["engineer_scope"] = engineer["scope"]
    inc["van"] = engineer["van"]


def _solve_on_site(inc: dict, excess: int) -> int:
    """On-site minutes that make the response excess exactly `excess` under the
    revision the dispatch instant selects. Keeps the finding band structurally pinned."""
    revision = revision_for(inc["dispatch_utc"])
    allowance = RESPONSE_TARGET + travel_allowance(inc, revision)
    carried = inc.get("handback_delta_min", 0)
    fixed = inc["travel_min"] + carried
    if REVISIONS[revision]["clock_start"] == "dispatch":
        fixed += inc["ack_delay_min"]
    if not REVISIONS[revision]["parts_wait_suspends"]:
        fixed += inc["parts_wait_min"]
    return allowance + excess - fixed


def apply_plants(incidents: list, people: dict) -> None:
    def plant(day, slot, overrides, tag, flags=(), excess=None):
        inc = _find(incidents, day, slot)
        _reassign_to_employed(inc, people)
        if "local_dispatch" in overrides:
            inc["local_dispatch"] = overrides["local_dispatch"]
            inc["dispatch_utc"] = instant_from_local(day, overrides["local_dispatch"])
        inc.update({k: v for k, v in overrides.items() if k != "local_dispatch"})
        if "travel_min" in overrides:
            inc["telemetry_travel_min"] = overrides["travel_min"]
        for flag in flags:
            inc[flag] = True
        if excess is not None:
            inc["on_site_min"] = _solve_on_site(inc, excess)
            inc["planted_excess"] = excess
        inc["planted"].append(tag)
        _retime(inc)
        return inc

    for day, slot, excess, overrides in CORE_RESPONSE_PLANTS:
        plant(day, slot, overrides, "core-response", excess=excess)
    for day, slot, excess, overrides in ACK_DELAY_PLANTS:
        plant(day, slot, dict(overrides, ack_delay_min=ACK_TARGET + excess),
              "ack-delay")
    for day, slot, excess, overrides in TRAVEL_CAP_PLANTS:
        plant(day, slot, overrides, "travel-cap", excess=excess)
    for day, slot, excess, overrides in PARTS_WAIT_PLANTS:
        plant(day, slot, overrides, "parts-wait", excess=excess)
    for day, slot, excess, overrides in REMOTE_LATE_PLANTS:
        plant(day, slot, overrides, "remote-late", excess=excess)
    for day, slot, excess, overrides in REVISION_SPLIT_PLANTS:
        plant(day, slot, overrides, "revision-split", ("revision_split",), excess=excess)
    for day, slot, excess, overrides in CERTIFICATE_PLANTS:
        plant(day, slot, overrides, "certificate", ("certificate_governed",), excess=excess)
    for day, slot, excess, overrides in BADGE_EXPORT_PLANTS:
        plant(day, slot, overrides, "badge-export", ("badge_export_sourced",), excess=excess)
    telemetry = []
    for day, slot, excess, overrides in TELEMETRY_PLANTS:
        telemetry.append(plant(day, slot, overrides, "telemetry",
                               ("telemetry_corrupt",), excess=excess))
    for inc in telemetry[1:]:
        inc["van"] = telemetry[0]["van"]

    day, slot, excess, overrides = CROSS_MODAL_PLANT
    plant(day, slot, overrides, "cross-modal", ("cross_modal", "has_media"), excess=excess)
    day, slot, overrides = HANDBACK_CONTROL_PLANT
    plant(day, slot, overrides, "handback-control", ("handback_control", "has_media"))
    day, slot, overrides = NEGATIVE_CONTROL_PLANT
    plant(day, slot, overrides, "negative-control", ("negative_control",))


def cause_of(inc: dict, revision: str) -> str:
    rev = REVISIONS[revision]
    if inc.get("cross_modal"):
        return "HANDBACK_DOCUMENT_CONFLICT"
    if inc.get("telemetry_corrupt"):
        return "TELEMETRY_TOTAL_MISMATCH"
    if inc.get("badge_export_sourced"):
        return "BADGE_OFFSET_MISMATCH"
    if inc.get("certificate_governed"):
        return "CERTIFICATE_OVERRIDE"
    if rev["travel_basis"] == "telemetry-recorded-capped" \
            and inc["telemetry_travel_min"] > rev["travel_cap_minutes"]:
        return "TRAVEL_CAP_BREACH"
    if not rev["parts_wait_suspends"] and inc["parts_wait_min"] >= PARTS_WAIT_FLOOR_B:
        return "PARTS_WAIT_UNSUSPENDED"
    first = inc.get("remote_attempt_min")
    if first is not None and first > REMOTE_WINDOW_C:
        return "REMOTE_ATTEMPT_LATE"
    return "RESPONSE_TARGET"


def find_incident_exceedances(inc: dict) -> list:
    """Typed exceedances for one dispatch record under the revision its dispatch selects."""
    revision = revision_for(inc["dispatch_utc"])
    out = []
    allowance = allowance_minutes(inc, revision)
    actual = actual_minutes(inc, revision)
    if actual > allowance:
        out.append((cause_of(inc, revision), allowance, actual, actual - allowance))
    delay = ack_delay_minutes(inc)
    if delay > ACK_TARGET:
        out.append(("ACKNOWLEDGEMENT_DELAY", ACK_TARGET, delay, delay - ACK_TARGET))
    return [(t, lim, act, exc) for (t, lim, act, exc) in out if exc > 0]


def partition_of(inc: dict, ftype: str) -> str:
    if inc.get("cross_modal"):
        return "cross-modal"
    if inc.get("telemetry_corrupt"):
        return "corrupted-telemetry"
    if inc.get("badge_export_sourced"):
        return "utc-export"
    if inc.get("certificate_governed"):
        return "certificate-override"
    if inc.get("revision_split"):
        return "revision-split"
    if ftype == "TRAVEL_CAP_BREACH":
        return "travel-allowance"
    if ftype == "PARTS_WAIT_UNSUSPENDED":
        return "suspended-clock"
    if ftype == "REMOTE_ATTEMPT_LATE":
        return "remote-attempt"
    return "core-response"


PARTITION_WEIGHT = {
    "core-response": 1,
    "travel-allowance": 3,
    "suspended-clock": 3,
    "remote-attempt": 3,
    "revision-split": 5,
    "certificate-override": 5,
    "utc-export": 5,
    "corrupted-telemetry": 5,
    "cross-modal": 5,
}

SHORTFALL_TYPES = ()


def reference_findings(incidents: list) -> list:
    findings = []
    for inc in sorted(incidents, key=lambda i: (i["dispatch_utc"], i["incident_ref"])):
        revision = revision_for(inc["dispatch_utc"])
        for ftype, limit, actual, excess in find_incident_exceedances(inc):
            findings.append({
                "engineer_id": inc["engineer_id"],
                "incident_ref": inc["incident_ref"],
                "finding_type": ftype,
                "revision": REVISIONS[revision]["label"],
                "revision_key": revision,
                "allowance_minutes": limit,
                "actual_minutes": actual,
                "excess_minutes": excess,
                "partition": partition_of(inc, ftype),
                "basis": "acknowledgement-delay" if ftype == "ACKNOWLEDGEMENT_DELAY"
                         else "response-excess",
            })
    findings.sort(key=lambda f: (f["incident_ref"], f["finding_type"]))
    return findings


def world_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
