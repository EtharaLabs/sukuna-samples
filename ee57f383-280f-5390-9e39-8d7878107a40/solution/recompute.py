"""Recompute slot-1 ground truth from the world as it stands.

The single source the verifier calls. Reads the same overlay bytes the light-servers
sidecar loads ($COMPLEXMCP_WORLD_DATA, or --world-data), applies every trigger in
_LightNotion.rule.json, and emits the post-mutation reference finding set, totals, notice
set, corrections set and annotation set as JSON on stdout.

Pure function of the world state it reads: no clock, no randomness, no network, no
environment beyond the world directory, stdlib only. Never reads a statement literal --
every figure is derived from a record field.

    PYTHONDONTWRITEBYTECODE=1 uv run --project /path/to/trinity --no-dev \\
        python solution/recompute.py --world-data environment/light-servers/world_data
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

PERIOD_START = datetime(2026, 10, 12, tzinfo=timezone.utc)
PERIOD_DAYS = 28
EDITION4_FIRST_DAY = 14
EDITION4_EFFECTIVE = datetime(2026, 10, 26, tzinfo=timezone.utc)
BST_END_UTC = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)

DB_REGISTER = "db-kd-driver-register"
DB_EDITIONS = "db-kd-wt7-editions"
DB_CARD = "db-kd-tacho-card-downloads"
DB_UNIT = "db-kd-tacho-unit-blocks"
DB_CERTS = "db-kd-manual-entry-certificates"
DB_ROSACT = "db-kd-roster-actuals-feed"
DB_INFR = "db-kd-infringement-index"
DB_TSHEET = "db-kd-agency-timesheet-index"
DB_FINDINGS = "db-kd-period-findings"
DB_CORRECTIONS = "db-kd-corrections-register"
DB_CLOSE = "db-kd-period-close-ledger"

DAILY_DRIVING_LIMIT = 540
CONTINUOUS_DRIVING_LIMIT = 270
BREAK_REQUIRED = 45
DAILY_REST_LIMIT = 660
WEEKLY_REST_LIMIT = 2700
DAILY_WORK_LIMIT = 660

EDITIONS = {
    3: {"label": "WT-7 Ed 3", "night_from": 0, "night_to": 240, "night_work_limit": 480,
        "min_break_segment": 15, "poa_is_working_time": False,
        "weekly_basis": "fixed-calendar-week", "weekly_limit": 3600},
    4: {"label": "WT-7 Ed 4", "night_from": 1380, "night_to": 300, "night_work_limit": 420,
        "min_break_segment": 30, "poa_is_working_time": True,
        "weekly_basis": "rolling-7-day-reference-period", "weekly_limit": 3360},
}

SHORTFALL_TYPES = ("BREAK_COMPOSITION", "DAILY_REST", "WEEKLY_REST")
NOTICE_SUBJECT = ("Brantlow Distribution Ltd - drivers' hours findings "
                  "2026-10-12 to 2026-11-08 - %s")
ANNOTATION_LINE = "WT-7 AUDIT 2026-11-10: period findings recorded; notice issued to %s"


def parse_instant(text: str) -> datetime:
    value = str(text).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def depot_offset_minutes(utc: datetime) -> int:
    return 60 if utc < BST_END_UTC else 0


def depot_local(utc: datetime) -> datetime:
    return utc + timedelta(minutes=depot_offset_minutes(utc))


def local_minute_of_day(utc: datetime) -> int:
    shown = depot_local(utc)
    return shown.hour * 60 + shown.minute


def period_day(utc: datetime) -> int:
    return (depot_local(utc).date() - PERIOD_START.date()).days


def edition_for(utc_start: datetime) -> int:
    return 4 if depot_local(utc_start) >= EDITION4_EFFECTIVE else 3


def spans_clock_change(start: datetime, end: datetime) -> bool:
    return start < BST_END_UTC < end


def load_world(world_dir: str) -> dict:
    out = {}
    for name in sorted(os.listdir(world_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(world_dir, name), encoding="utf-8") as fh:
            out[name[:-5]] = json.load(fh)
    return out


def value_of(props: dict, key: str, default=None):
    cell = props.get(key)
    if cell is None:
        return default
    if isinstance(cell, dict) and "value" in cell:
        return cell["value"]
    return cell


def post_close_triggers(rule: dict) -> list:
    return [t for t in rule.get("triggers", [])
            if t.get("when", {}).get("database") == DB_CLOSE]


def apply_triggers(notion: dict, rule: dict) -> list:
    """Land every trigger's `set` block on the page properties, as the sidecar does."""
    applied = []
    properties = notion.setdefault("properties", {})
    for trigger in rule.get("triggers", []):
        for change in trigger.get("set", []):
            target = properties.setdefault(change["page"], {})
            for key, new in change["properties"].items():
                before = value_of(target, key)
                kind = target.get(key, {}).get("type", "rich_text") \
                    if isinstance(target.get(key), dict) else "rich_text"
                target[key] = {"type": kind, "value": new}
                applied.append({
                    "trigger": trigger["id"],
                    "fires_on": "%s create number %s in %s" % (
                        trigger["when"].get("tool"), trigger["when"].get("count"),
                        trigger["when"].get("database")),
                    "page": change["page"],
                    "field": key,
                    "old_value": before,
                    "new_value": new,
                    "post_close": trigger.get("when", {}).get("database") == DB_CLOSE,
                })
    return applied


def pages_in(notion: dict, database_id: str) -> list:
    return [p for p in notion.get("pages", [])
            if p.get("parent_type") == "database" and p.get("parent_id") == database_id
            and not p.get("archived")]


def roster_index(monday: dict) -> dict:
    by_item = {}
    for row in monday.get("column_values", []):
        by_item.setdefault(row["item_id"], {})[row["column_id"]] = row.get("text")
    out = {}
    for cells in by_item.values():
        ref = cells.get("duty_ref")
        if ref:
            out[ref] = cells
    return out


def break_segments(pattern: str) -> list:
    return [int(x) for x in str(pattern).split("+") if str(x).strip()]


def qualifying_break(pattern: str, edition: int) -> int:
    floor = EDITIONS[edition]["min_break_segment"]
    return sum(s for s in break_segments(pattern) if s >= floor)


def working_minutes(duty: dict, edition: int) -> int:
    total = duty["drive_min"] + duty["other_work_min"]
    if EDITIONS[edition]["poa_is_working_time"]:
        total += duty["poa_min"]
    return total


def touches_night_window(duty: dict, edition: int) -> bool:
    ed = EDITIONS[edition]
    start = local_minute_of_day(duty["start_utc"])
    for offset in range(0, duty["elapsed_min"] + 1, 15):
        minute = (start + offset) % 1440
        if ed["night_from"] <= ed["night_to"]:
            if ed["night_from"] <= minute < ed["night_to"]:
                return True
        elif minute >= ed["night_from"] or minute < ed["night_to"]:
            return True
    return False


def build_duties(notion: dict, monday: dict) -> list:
    roster = roster_index(monday)
    properties = notion.get("properties", {})
    duties = []

    for page in pages_in(notion, DB_CARD):
        props = properties.get(page["id"], {})
        start = parse_instant(value_of(props, "StartUtc"))
        duties.append({
            "duty_ref": value_of(props, "DutyRef"),
            "driver_id": value_of(props, "DriverId"),
            "vehicle": value_of(props, "VehicleRegistration"),
            "start_utc": start,
            "end_utc": parse_instant(value_of(props, "EndUtc")),
            "elapsed_min": int(value_of(props, "ElapsedTrueMinutes")),
            "drive_min": int(value_of(props, "DrivingMinutes")),
            "other_work_min": int(value_of(props, "OtherWorkMinutes")),
            "poa_min": int(value_of(props, "PeriodsOfAvailabilityMinutes")),
            "break_pattern": value_of(props, "BreakPattern"),
            "longest_continuous_min": int(value_of(props, "LongestContinuousDrivingMinutes")),
            "daily_rest_before_min": int(value_of(props, "DailyRestBeforeMinutes")),
            "weekly_rest_before_min": int(value_of(props, "WeeklyRestBeforeMinutes")),
            "governed_by": "tachograph card download",
            "record_ref": value_of(props, "DownloadRef"),
            "page_id": page["id"],
        })

    for page in pages_in(notion, DB_CERTS):
        props = properties.get(page["id"], {})
        if str(value_of(props, "SignatureStatus", "")).strip().lower() != "signed":
            continue
        ref = value_of(props, "DutyRef")
        cells = roster.get(ref)
        if cells is None:
            continue
        start = parse_instant(cells["planned_start"])
        end = parse_instant(cells["planned_end"])
        duties.append({
            "duty_ref": ref,
            "driver_id": value_of(props, "DriverId"),
            "vehicle": cells.get("vehicle"),
            "start_utc": start,
            "end_utc": end,
            "elapsed_min": int((end - start).total_seconds() // 60),
            "drive_min": int(value_of(props, "DeclaredDrivingMinutes")),
            "other_work_min": int(value_of(props, "DeclaredOtherWorkMinutes")),
            "poa_min": int(value_of(props, "DeclaredPeriodsOfAvailabilityMinutes")),
            "break_pattern": value_of(props, "DeclaredBreakPattern"),
            "longest_continuous_min": None,
            "daily_rest_before_min": int(value_of(props, "DeclaredDailyRestBeforeMinutes")),
            "weekly_rest_before_min": 0,
            "governed_by": "signed manual entry certificate",
            "record_ref": value_of(props, "CertificateRef"),
            "page_id": page["id"],
        })

    duties.sort(key=lambda d: (d["start_utc"], d["duty_ref"]))
    return duties


def duty_exceedances(duty: dict) -> list:
    edition = edition_for(duty["start_utc"])
    ed = EDITIONS[edition]
    out = []
    if duty["drive_min"] > DAILY_DRIVING_LIMIT:
        out.append(("DAILY_DRIVING", DAILY_DRIVING_LIMIT, duty["drive_min"]))
    if duty["longest_continuous_min"] is not None \
            and duty["longest_continuous_min"] > CONTINUOUS_DRIVING_LIMIT:
        out.append(("CONTINUOUS_DRIVING", CONTINUOUS_DRIVING_LIMIT,
                    duty["longest_continuous_min"]))
    qualifying = qualifying_break(duty["break_pattern"], edition)
    if qualifying < BREAK_REQUIRED:
        out.append(("BREAK_COMPOSITION", BREAK_REQUIRED, qualifying))
    if duty["daily_rest_before_min"] and duty["daily_rest_before_min"] < DAILY_REST_LIMIT:
        out.append(("DAILY_REST", DAILY_REST_LIMIT, duty["daily_rest_before_min"]))
    if duty["weekly_rest_before_min"] and duty["weekly_rest_before_min"] < WEEKLY_REST_LIMIT:
        out.append(("WEEKLY_REST", WEEKLY_REST_LIMIT, duty["weekly_rest_before_min"]))
    work = working_minutes(duty, edition)
    if touches_night_window(duty, edition) and work > ed["night_work_limit"]:
        out.append(("NIGHT_WORK", ed["night_work_limit"], work))
    if work > DAILY_WORK_LIMIT:
        out.append(("AVAILABILITY", DAILY_WORK_LIMIT, work))

    rows = []
    for ftype, limit, actual in out:
        excess = (limit - actual) if ftype in SHORTFALL_TYPES else (actual - limit)
        if excess > 0:
            rows.append((ftype, edition, limit, actual, excess))
    return rows


def weekly_exceedances(duties: list) -> list:
    by_driver = {}
    for duty in duties:
        by_driver.setdefault(duty["driver_id"], []).append(duty)
    out = []
    for driver_id in sorted(by_driver):
        rows = sorted(by_driver[driver_id], key=lambda d: (d["start_utc"], d["duty_ref"]))
        for week in range(4):
            days = set(range(week * 7, week * 7 + 7))
            member = [d for d in rows
                      if period_day(d["start_utc"]) in days and edition_for(d["start_utc"]) == 3]
            if not member:
                continue
            total = sum(working_minutes(d, 3) for d in member)
            if total > EDITIONS[3]["weekly_limit"]:
                out.append((member[-1], 3, EDITIONS[3]["weekly_limit"], total))
        for anchor in range(EDITION4_FIRST_DAY, PERIOD_DAYS):
            window = set(range(anchor - 6, anchor + 1))
            member = [d for d in rows
                      if period_day(d["start_utc"]) in window and edition_for(d["start_utc"]) == 4]
            if not member:
                continue
            total = sum(working_minutes(d, 4) for d in member)
            if total > EDITIONS[4]["weekly_limit"]:
                out.append((member[-1], 4, EDITIONS[4]["weekly_limit"], total))
                break
    return out


def partition_of(duty: dict, ftype: str, unit_blocks: dict) -> str:
    if spans_clock_change(duty["start_utc"], duty["end_utc"]):
        return "clock-change"
    if duty["governed_by"] == "signed manual entry certificate":
        return "override"
    if duty["duty_ref"] in unit_blocks:
        return "contradiction"
    if ftype == "NIGHT_WORK":
        return "night-work"
    if ftype in ("BREAK_COMPOSITION", "AVAILABILITY", "ROLLING_WORKING_TIME"):
        return "edition-split"
    if ftype in ("DAILY_REST", "WEEKLY_REST"):
        return "rest"
    return "core-daily-driving"


PARTITION_WEIGHT = {"core-daily-driving": 1, "rest": 3, "edition-split": 5, "override": 5,
                    "night-work": 5, "clock-change": 5, "contradiction": 5}


def contradicting_refs(notion: dict) -> dict:
    """Duty refs whose keyed actuals disagree with the card download."""
    properties = notion.get("properties", {})
    card = {}
    for page in pages_in(notion, DB_CARD):
        props = properties.get(page["id"], {})
        card[value_of(props, "DutyRef")] = int(value_of(props, "DrivingMinutes"))
    out = {}
    for page in pages_in(notion, DB_ROSACT):
        props = properties.get(page["id"], {})
        ref = value_of(props, "DutyRef")
        keyed = value_of(props, "KeyedDrivingMinutes")
        if ref in card and keyed is not None and int(keyed) != card[ref]:
            out[ref] = {"keyed": int(keyed), "card": card[ref], "page": page["id"]}
    return out


def evidence_refs(duty: dict) -> str:
    return "%s;KD-GATE-%s" % (duty["record_ref"],
                              depot_local(duty["start_utc"]).strftime("%Y%m%d"))


def reference_findings(notion: dict, monday: dict) -> list:
    duties = build_duties(notion, monday)
    contradictions = contradicting_refs(notion)
    findings = []
    for duty in duties:
        for ftype, edition, limit, actual, excess in duty_exceedances(duty):
            findings.append({
                "Driver": duty["driver_id"],
                "DutyRef": duty["duty_ref"],
                "FindingType": ftype,
                "EditionApplied": EDITIONS[edition]["label"],
                "LimitMinutes": limit,
                "ActualMinutes": actual,
                "ExcessMinutes": excess,
                "EvidenceRefs": evidence_refs(duty),
                "partition": partition_of(duty, ftype, contradictions),
                "governed_by": duty["governed_by"],
                "basis": "shortfall" if ftype in SHORTFALL_TYPES else "excess",
            })
    for duty, edition, limit, total in weekly_exceedances(duties):
        findings.append({
            "Driver": duty["driver_id"],
            "DutyRef": duty["duty_ref"],
            "FindingType": "ROLLING_WORKING_TIME",
            "EditionApplied": EDITIONS[edition]["label"],
            "LimitMinutes": limit,
            "ActualMinutes": total,
            "ExcessMinutes": total - limit,
            "EvidenceRefs": evidence_refs(duty),
            "partition": "edition-split",
            "governed_by": duty["governed_by"],
            "basis": "excess",
        })
    findings.sort(key=lambda f: (f["DutyRef"], f["FindingType"]))
    return findings


def driver_addresses(notion: dict) -> dict:
    properties = notion.get("properties", {})
    out = {}
    for page in pages_in(notion, DB_REGISTER):
        props = properties.get(page["id"], {})
        out[value_of(props, "DriverId")] = {
            "name": value_of(props, "DriverName"),
            "address": value_of(props, "ContactAddress"),
            "scope": value_of(props, "AuditScope"),
            "page": page["id"],
        }
    return out


def notice_set(findings: list, notion: dict) -> list:
    register = driver_addresses(notion)
    by_driver = {}
    for finding in findings:
        by_driver.setdefault(finding["Driver"], []).append(finding)
    out = []
    for driver_id in sorted(by_driver):
        rows = sorted(by_driver[driver_id], key=lambda f: (f["DutyRef"], f["FindingType"]))
        entry = register.get(driver_id, {})
        out.append({
            "driver_id": driver_id,
            "driver_name": entry.get("name"),
            "to_address": entry.get("address"),
            "subject": NOTICE_SUBJECT % driver_id,
            "body_lines": ["%s %s limit %d actual %d excess %d" % (
                f["DutyRef"], f["FindingType"], f["LimitMinutes"],
                f["ActualMinutes"], f["ExcessMinutes"]) for f in rows],
            "finding_count": len(rows),
        })
    return out


def annotation_set(notion: dict, notified: set) -> list:
    properties = notion.get("properties", {})
    out = []
    for page in pages_in(notion, DB_INFR):
        props = properties.get(page["id"], {})
        if str(value_of(props, "SignatureStatus", "")).strip().lower() != "signed":
            continue
        driver_id = value_of(props, "DriverId")
        if driver_id not in notified:
            continue
        out.append({
            "report_ref": value_of(props, "ReportRef"),
            "service_desk_number": value_of(props, "ServiceDeskRef"),
            "driver_id": driver_id,
            "annotation_line": ANNOTATION_LINE % driver_id,
            "index_page": page["id"],
        })
    out.sort(key=lambda a: a["report_ref"])
    return out


def correction_set(applied: list, notion: dict) -> list:
    properties = notion.get("properties", {})
    ref_of = {}
    for page in notion.get("pages", []):
        props = properties.get(page["id"], {})
        for key in ("DownloadRef", "CertificateRef", "ReportRef", "TimesheetRef", "BlockRef"):
            if key in props:
                ref_of[page["id"]] = value_of(props, key)
                break
    decisive = ("DeclaredDrivingMinutes", "DrivingMinutes", "SignatureStatus", "Status")
    by_trigger = {}
    for change in applied:
        if not change["post_close"]:
            continue
        by_trigger.setdefault(change["trigger"], []).append(change)

    out = []
    for trigger in sorted(by_trigger):
        changes = by_trigger[trigger]
        head = next((c for c in changes if c["field"] in decisive), changes[0])
        props = properties.get(head["page"], {})
        out.append({
            "trigger": trigger,
            "RecordRef": ref_of.get(head["page"], head["page"]),
            "FieldChanged": head["field"],
            "OldValue": head["old_value"],
            "NewValue": head["new_value"],
            "affects_duty_ref": value_of(props, "DutyRef")
            or value_of(props, "CorroboratesDutyRef"),
            "affects_driver": value_of(props, "DriverId"),
            "also_changed": sorted(c["field"] for c in changes if c is not head),
            "fires_on": head["fires_on"],
            "record_page": head["page"],
        })
    return out


def recompute(world_dir: str) -> dict:
    world = load_world(world_dir)
    notion = world["LightNotion"]
    monday = world["LightMonday"]
    with open(os.path.join(world_dir, "_LightNotion.rule.json"), encoding="utf-8") as fh:
        rule = json.load(fh)

    applied = apply_triggers(notion, rule)
    findings = reference_findings(notion, monday)
    notices = notice_set(findings, notion)
    notified = {n["driver_id"] for n in notices}
    annotations = annotation_set(notion, notified)
    corrections = correction_set(applied, notion)

    totals = {
        "FindingCount": len(findings),
        "TotalExcessMinutes": sum(f["ExcessMinutes"] for f in findings),
        "DriversAffected": len(notified),
    }
    partitions = {}
    types = {}
    editions = {}
    for finding in findings:
        partitions[finding["partition"]] = partitions.get(finding["partition"], 0) + 1
        types[finding["FindingType"]] = types.get(finding["FindingType"], 0) + 1
        editions[finding["EditionApplied"]] = editions.get(finding["EditionApplied"], 0) + 1

    return {
        "period": {"start": "2026-10-12", "end": "2026-11-08",
                   "edition_4_effective": "2026-10-26",
                   "clock_change": "2026-10-25T02:00 BST to 01:00 GMT"},
        "close_record": {
            "PeriodStart": "2026-10-12", "PeriodEnd": "2026-11-08",
            "FindingCount": totals["FindingCount"],
            "TotalExcessMinutes": totals["TotalExcessMinutes"],
            "DriversAffected": totals["DriversAffected"],
            "CloseState": "CLOSED",
        },
        "ticket_lines": [
            "AUDIT-SUMMARY findings=%d" % totals["FindingCount"],
            "AUDIT-SUMMARY excess-minutes=%d" % totals["TotalExcessMinutes"],
            "AUDIT-SUMMARY drivers-notified=%d" % totals["DriversAffected"],
        ],
        "totals": totals,
        "by_partition": dict(sorted(partitions.items())),
        "by_type": dict(sorted(types.items())),
        "by_edition": dict(sorted(editions.items())),
        "weighted_positive": sum(PARTITION_WEIGHT[f["partition"]] for f in findings),
        "findings": findings,
        "notices": notices,
        "annotations": annotations,
        "corrections": corrections,
        "applied_changes": applied,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="recompute")
    ap.add_argument("--world-data",
                    default=os.environ.get("COMPLEXMCP_WORLD_DATA", "/world_data"))
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    truth = recompute(args.world_data)
    if args.summary:
        print("findings            %d" % truth["totals"]["FindingCount"])
        print("total excess mins   %d" % truth["totals"]["TotalExcessMinutes"])
        print("drivers notified    %d" % truth["totals"]["DriversAffected"])
        print("notices             %d" % len(truth["notices"]))
        print("annotations         %d" % len(truth["annotations"]))
        print("corrections         %d" % len(truth["corrections"]))
        print("by type             %s" % truth["by_type"])
        print("by partition        %s" % truth["by_partition"])
        print("by edition          %s" % truth["by_edition"])
        print("weighted positive   %d" % truth["weighted_positive"])
        print("ticket lines        %s" % " | ".join(truth["ticket_lines"]))
        return 0
    json.dump(truth, sys.stdout, indent=1, sort_keys=True, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
