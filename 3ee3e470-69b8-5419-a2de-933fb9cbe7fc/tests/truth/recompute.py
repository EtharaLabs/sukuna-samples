"""Recompute the Calderwick FSR-9 response audit ground truth from the world as it stands.

Independent re-derivation leg. This module imports nothing from the world generator: every
FSR-9 rule constant below is re-declared from the published revision documents and the
response audit field guide, and every figure is read out of the emitted world bytes that
the light-servers sidecar loads ($COMPLEXMCP_WORLD_DATA, or --world-data). If this module
and the generator disagree on any census figure, the world is wrong.

Pure function of the world directory it reads: no clock, no randomness, no network, no
model, stdlib only. No statement literal is ever trusted; every minute figure comes from a
record field.

    PYTHONDONTWRITEBYTECODE=1 python3 solution/recompute.py \\
        --world-data environment/light-servers/world_data --summary
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

PERIOD_START = "2026-10-05"
PERIOD_END = "2026-11-01"
OPERATOR = "Thornby Field Services Ltd"

SUMMER_END_UTC = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
REVISION_C_LOCAL_START = datetime(2026, 10, 19, tzinfo=timezone.utc)

RESPONSE_TARGET = 120
ACK_TARGET = 20
TRAVEL_FIXED_B = 45
TRAVEL_CAP_C = 60
REMOTE_WINDOW_C = 15
PARTS_WAIT_FLOOR_B = 30

REVISIONS = {
    "B": {"label": "FSR-9 Rev B", "clock_start": "dispatch",
          "travel_basis": "fixed-allowance", "parts_wait_suspends": False,
          "remote_counts_as_response": False},
    "C": {"label": "FSR-9 Rev C", "clock_start": "acknowledgement",
          "travel_basis": "telemetry-recorded-capped", "parts_wait_suspends": True,
          "remote_counts_as_response": True},
}

DB_PAGING = "db-crn-paging-archive"
DB_CERTS = "db-crn-handback-certificates"
DB_REGISTER = "db-crn-engineer-register"
DB_TELEMETRY = "db-crn-van-telemetry-summaries"
DB_LEGS = "db-crn-van-leg-records"
DB_REMOTE = "db-crn-remote-attempt-log"
DB_PARTS = "db-crn-parts-wait-log"
DB_REPORTS = "db-crn-incident-report-index"
DB_FINDINGS = "db-crn-response-findings"
DB_CLOSE = "db-crn-period-close-ledger"

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

NOTICE_SUBJECT = ("%s - FSR-9 response findings %s to %s - %%s"
                  % (OPERATOR, PERIOD_START, PERIOD_END))
NOTICE_LINE = "%s %s allowance %d actual %d excess %d"
ANNOTATION_LINE = ("FSR-9 AUDIT 2026-11-03: response findings recorded; "
                   "notice issued to %s")

# The badge access export is published outside the world overlay directory (it ships as a
# task_data / drive_blobs document rendered in archive clock terms with no offset named),
# so no world record field marks which dispatches the audit sourced from it. The two
# references the export is decisive for are re-declared here, mirroring the design's own
# badge-sourced row set; every minute figure for them is still derived from world records.
BADGE_EXPORT_INCIDENTS = ("CRN-1110-124", "CRN-2610-110")

# A secondary log restamped with either of these provenance phrases moved after the audit
# relied on it. Field guide section 6 settles the consequence: the recorded finding keeps
# the figure it was raised on and a correction is filed; the finding is never deleted.
POST_RELIANCE_STAMPS = ("amended after period end", "corrected log")

REVISION_BOUNDARY_BAND = (23 * 60, 2 * 60)

MEDIA_FACTS_NAME = "media_facts.json"
MEDIA_FACTS_ENV = "SUKUNA_MEDIA_FACTS"
MEDIA_FACTS_MOUNT = os.path.join(os.sep, "opt", "truth", MEDIA_FACTS_NAME)
MEDIA_FACTS_SCHEMA = "sukuna.slot1.media-facts/v1"
MEDIA_PAIR_KINDS = frozenset(("jobsheet-png", "handback-wav"))


def parse_instant(text):
    value = str(text).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def optional_instant(text):
    value = "" if text is None else str(text).strip()
    if not value:
        return None
    return parse_instant(value)


def depot_offset_minutes(utc):
    return 60 if utc < SUMMER_END_UTC else 0


def depot_local(utc):
    return utc + timedelta(minutes=depot_offset_minutes(utc))


def local_minute_of_day(utc):
    shown = depot_local(utc)
    return shown.hour * 60 + shown.minute


def revision_for(dispatch_utc):
    return "C" if depot_local(dispatch_utc) >= REVISION_C_LOCAL_START else "B"


def in_boundary_band(utc):
    low, high = REVISION_BOUNDARY_BAND
    minute = local_minute_of_day(utc)
    return minute >= low or minute < high


def load_world(world_dir):
    out = {}
    for name in sorted(os.listdir(world_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(world_dir, name), encoding="utf-8") as fh:
            out[name[:-5]] = json.load(fh)
    return out


def value_of(props, key, default=None):
    cell = props.get(key)
    if cell is None:
        return default
    if isinstance(cell, dict) and "value" in cell:
        return cell["value"]
    return cell


def minutes_of(props, key, default=0):
    raw = value_of(props, key, default)
    if raw is None or isinstance(raw, (dict, list)):
        return int(default)
    return int(str(raw))


def pages_in(notion, database_id):
    return [p for p in notion.get("pages", [])
            if p.get("parent_type") == "database" and p.get("parent_id") == database_id
            and not p.get("archived")]


def apply_triggers(notion, rule):
    """Land every trigger's `set` block on the page properties, as the sidecar does."""
    applied = []
    properties = notion.setdefault("properties", {})
    for trigger in rule.get("triggers", []):
        when = trigger.get("when", {})
        for change in trigger.get("set", []):
            target = properties.setdefault(change["page"], {})
            for key in sorted(change["properties"]):
                new = change["properties"][key]
                before = value_of(target, key)
                cell = target.get(key)
                kind = cell.get("type", "rich_text") if isinstance(cell, dict) else "rich_text"
                target[key] = {"type": kind, "value": new}
                applied.append({
                    "trigger": trigger.get("id"),
                    "fires_on": "%s create number %s in %s" % (
                        when.get("tool"), when.get("count"), when.get("database")),
                    "page": change["page"],
                    "field": key,
                    "old_value": before,
                    "new_value": new,
                    "post_close": when.get("database") == DB_CLOSE,
                })
    return applied


def roster_identity(monday):
    """The on-call roster board is the only carrier that resolves a dispatch to a person."""
    by_item = {}
    for row in monday.get("column_values", []):
        by_item.setdefault(row["item_id"], {})[row["column_id"]] = row.get("text")
    out = {}
    for cells in by_item.values():
        ref = cells.get("incident_ref")
        if ref:
            out[ref] = {"engineer_id": cells.get("engineer_id"),
                        "engineer_name": cells.get("engineer_name")}
    return out


def media_facts_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.environ.get(MEDIA_FACTS_ENV),
                      MEDIA_FACTS_MOUNT,
                      os.path.join(here, MEDIA_FACTS_NAME),
                      os.path.join(here, os.pardir, "solution", MEDIA_FACTS_NAME)):
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def load_media_facts():
    """The rendered evidence media carry no machine readable text, so the hand-back the
    job sheet and voice note state is published out of band in media_facts.json. It is a
    required input: without it no hand-back supersession can be graded, so a missing or
    malformed file fails closed rather than falling back to the paging heartbeat."""
    path = media_facts_path()
    if path is None:
        raise RuntimeError(
            "media facts not found: set %s, or place %s beside recompute.py, or mount it "
            "at %s" % (MEDIA_FACTS_ENV, MEDIA_FACTS_NAME, MEDIA_FACTS_MOUNT))
    with open(path, encoding="utf-8") as fh:
        facts = json.load(fh)
    schema = str(facts.get("schema", ""))
    if schema != MEDIA_FACTS_SCHEMA:
        raise RuntimeError("media facts schema is %r, expected %r"
                           % (schema, MEDIA_FACTS_SCHEMA))
    if not isinstance(facts.get("artefacts"), list) or not facts["artefacts"]:
        raise RuntimeError("media facts carry no artefacts: %s" % path)
    facts["source_path"] = path
    return facts


def media_evidence(facts):
    """Incident references whose evidence folder carries both a job sheet image and the
    engineer's own hand-back voice note. That countersigned pair is the documentation the
    field guide ranks above the auto-logged clear line, and where it contradicts the
    paging heartbeat the instant it states governs the hand-back."""
    seen = {}
    for item in facts["artefacts"]:
        ref = item.get("incident_ref")
        kind = item.get("kind")
        if not ref or kind not in MEDIA_PAIR_KINDS:
            continue
        entry = seen.setdefault(ref, {"kinds": set(), "stated": set(), "agrees": set(),
                                      "engineer_id": item.get("engineer_id"),
                                      "paths": []})
        entry["kinds"].add(kind)
        entry["stated"].add(str(item.get("stated_handback_local")))
        entry["agrees"].add(bool(item.get("agrees_with_paging")))
        entry["paths"].append(item.get("drive_path"))
    out = {}
    for ref, entry in seen.items():
        if entry["kinds"] != MEDIA_PAIR_KINDS:
            continue
        if len(entry["stated"]) != 1 or len(entry["agrees"]) != 1:
            raise RuntimeError("media facts disagree with themselves for %s" % ref)
        out[ref] = {
            "engineer_id": entry["engineer_id"],
            "agrees_with_paging": entry["agrees"].pop(),
            "stated_handback_utc": parse_instant(entry["stated"].pop()),
            "artefact_paths": sorted(p for p in entry["paths"] if p),
        }
    return out


def read_incidents(notion, monday, facts):
    properties = notion.get("properties", {})
    identity = roster_identity(monday)
    media = media_evidence(facts)
    incidents = {}

    for page in pages_in(notion, DB_PAGING):
        props = properties.get(page["id"], {})
        ref = value_of(props, "IncidentRef")
        who = identity.get(ref, {})
        incidents[ref] = {
            "incident_ref": ref,
            "site_code": value_of(props, "SiteCode"),
            "call_shape": value_of(props, "CallShape"),
            "dispatch_utc": parse_instant(value_of(props, "DispatchUtc")),
            "ack_utc": parse_instant(value_of(props, "AcknowledgedUtc")),
            "auto_clear_utc": parse_instant(value_of(props, "AutoLoggedClearUtc")),
            "paging_ref": value_of(props, "PagingRecordRef"),
            "engineer_id": who.get("engineer_id"),
            "engineer_name": who.get("engineer_name"),
            "travel_minutes": 0,
            "leg_ref": None,
            "van_code": None,
            "week_commencing": None,
            "parts_wait_minutes": 0,
            "parts_wait_relied": 0,
            "parts_ref": None,
            "parts_amended": False,
            "remote_minutes": None,
            "remote_relied": None,
            "remote_ref": None,
            "remote_amended": False,
            "certificate": None,
            "media": media.get(ref),
        }

    for page in sorted(pages_in(notion, DB_LEGS), key=lambda p: p["id"]):
        props = properties.get(page["id"], {})
        ref = value_of(props, "IncidentRef")
        row = incidents.get(ref)
        if row is None:
            continue
        row["travel_minutes"] += minutes_of(props, "TravelMinutes")
        row["van_code"] = value_of(props, "VanCode")
        row["week_commencing"] = value_of(props, "WeekCommencing")
        if row["leg_ref"] is None or value_of(props, "LegIndex") == 1:
            row["leg_ref"] = value_of(props, "LegRef")

    for page in pages_in(notion, DB_PARTS):
        props = properties.get(page["id"], {})
        row = incidents.get(value_of(props, "IncidentRef"))
        if row is None:
            continue
        logged = minutes_of(props, "LoggedWaitMinutes")
        source = str(value_of(props, "WaitSource", ""))
        amended = any(stamp in source for stamp in POST_RELIANCE_STAMPS)
        row["parts_ref"] = value_of(props, "WaitRef")
        row["parts_wait_minutes"] = logged
        row["parts_amended"] = amended
        row["parts_wait_relied"] = logged

    for page in pages_in(notion, DB_REMOTE):
        props = properties.get(page["id"], {})
        row = incidents.get(value_of(props, "IncidentRef"))
        if row is None:
            continue
        first = value_of(props, "FirstAttemptMinutesAfterDispatch")
        source = str(value_of(props, "AttemptSource", ""))
        row["remote_ref"] = value_of(props, "AttemptRef")
        row["remote_minutes"] = None if first is None else minutes_of(props, "FirstAttemptMinutesAfterDispatch")
        row["remote_amended"] = any(stamp in source for stamp in POST_RELIANCE_STAMPS)
        row["remote_relied"] = row["remote_minutes"]

    for page in pages_in(notion, DB_CERTS):
        props = properties.get(page["id"], {})
        row = incidents.get(value_of(props, "IncidentRef"))
        if row is None:
            continue
        row["certificate"] = {
            "certificate_ref": value_of(props, "CertificateRef"),
            "declared_utc": optional_instant(value_of(props, "DeclaredHandbackDepotLocal")),
            "signature_status": value_of(props, "SignatureStatus"),
            "countersigned_by": value_of(props, "CountersignedBy"),
            "page_id": page["id"],
        }

    return incidents


def off_rota_refs(incidents):
    """A dispatch whose depot local wall time is shared by no other dispatch of the same
    call shape was re-timed off the standing rota. Where that re-timed instant also falls
    in the band around midnight, the call straddles the revision boundary the period
    carries, and the finding it raises belongs to the revision-split partition."""
    counts = {}
    for row in incidents.values():
        key = (row["call_shape"], local_minute_of_day(row["dispatch_utc"]))
        counts[key] = counts.get(key, 0) + 1
    out = set()
    for ref, row in incidents.items():
        key = (row["call_shape"], local_minute_of_day(row["dispatch_utc"]))
        if counts[key] == 1 and in_boundary_band(row["dispatch_utc"]):
            out.add(ref)
    return out


def corrupt_block_refs(notion, incidents):
    """Weekly travel summary blocks are rollups. A block whose published total disagrees
    with the per-leg records for the same van and week is corrupted; the calls inside it
    are graded off the per-leg rows and carry the corrupted-telemetry partition."""
    properties = notion.get("properties", {})
    leg_totals = {}
    for row in incidents.values():
        key = (row["van_code"], row["week_commencing"])
        leg_totals[key] = leg_totals.get(key, 0) + row["travel_minutes"]
    bad = {}
    for page in pages_in(notion, DB_TELEMETRY):
        props = properties.get(page["id"], {})
        key = (value_of(props, "VanCode"), value_of(props, "WeekCommencing"))
        if value_of(props, "TotalTravelMinutes") is None:
            continue
        published = minutes_of(props, "TotalTravelMinutes")
        derived = leg_totals.get(key)
        if derived is not None and published != derived:
            bad[key] = {"block_ref": value_of(props, "BlockRef"),
                        "published_total": published,
                        "per_leg_total": derived}
    out = {}
    for ref, row in incidents.items():
        key = (row["van_code"], row["week_commencing"])
        if key in bad:
            out[ref] = bad[key]
    return out


def handback_instant(row, relied):
    """Signed hand-back documentation supersedes the auto-logged clear heartbeat. The
    countersigned job sheet and voice note pair outranks every workspace row, so where
    that pair contradicts the paging heartbeat the media facts settle the instant and no
    certificate field is consulted. Otherwise a countersigned certificate governs."""
    media = row["media"]
    if media is not None:
        if not media["agrees_with_paging"]:
            return media["stated_handback_utc"], True
        return row["auto_clear_utc"], False
    cert = row["certificate"]
    if cert is None:
        return row["auto_clear_utc"], False
    declared = cert["declared_utc"]
    if declared is None \
            or str(cert["signature_status"] or "").strip().lower() != "countersigned":
        return row["auto_clear_utc"], False
    return declared, declared != row["auto_clear_utc"]


def travel_allowance(row, revision):
    if REVISIONS[revision]["travel_basis"] == "fixed-allowance":
        return TRAVEL_FIXED_B
    return min(row["travel_minutes"], TRAVEL_CAP_C)


def parts_wait_for(row, relied):
    if relied and row["parts_amended"]:
        return row["parts_wait_relied"]
    return row["parts_wait_minutes"]


def remote_for(row, relied):
    if relied and row["remote_amended"]:
        return row["remote_relied"]
    return row["remote_minutes"]


def exceedances(row, relied):
    revision = revision_for(row["dispatch_utc"])
    rev = REVISIONS[revision]
    allowance = RESPONSE_TARGET + travel_allowance(row, revision)
    clear_utc, conflicts = handback_instant(row, relied)
    parts = parts_wait_for(row, relied)
    remote = remote_for(row, relied)

    if rev["remote_counts_as_response"] and remote is not None \
            and remote <= REMOTE_WINDOW_C:
        actual = remote
    else:
        start = row["ack_utc"] if rev["clock_start"] == "acknowledgement" \
            else row["dispatch_utc"]
        elapsed = int((clear_utc - start).total_seconds() // 60)
        actual = max(0, elapsed - (parts if rev["parts_wait_suspends"] else 0))

    out = []
    if actual > allowance:
        out.append(("RESPONSE", allowance, actual, actual - allowance, conflicts,
                    parts, remote))
    delay = int((row["ack_utc"] - row["dispatch_utc"]).total_seconds() // 60)
    if delay > ACK_TARGET:
        out.append(("ACKNOWLEDGEMENT_DELAY", ACK_TARGET, delay, delay - ACK_TARGET,
                    False, parts, remote))
    return revision, out


def classify(row, conflicts, parts, remote, revision, corrupt, off_rota):
    """Finding type and partition, in the precedence the field guide publishes: the
    cross-modal hand-back conflict first, then a corrupted rollup, then an export the
    audit had to convert, then a certificate that displaced the auto log, then the
    revision-specific allowance rules."""
    rev = REVISIONS[revision]
    if conflicts:
        return "HANDBACK_DOCUMENT_CONFLICT", "cross-modal"
    if corrupt:
        return "TELEMETRY_TOTAL_MISMATCH", "corrupted-telemetry"
    if row["incident_ref"] in BADGE_EXPORT_INCIDENTS:
        return "BADGE_OFFSET_MISMATCH", "utc-export"
    if row["certificate"] is not None:
        return "CERTIFICATE_OVERRIDE", "certificate-override"
    if rev["travel_basis"] == "telemetry-recorded-capped" \
            and row["travel_minutes"] > TRAVEL_CAP_C:
        return "TRAVEL_CAP_BREACH", "travel-allowance"
    if not rev["parts_wait_suspends"] and parts >= PARTS_WAIT_FLOOR_B:
        return "PARTS_WAIT_UNSUSPENDED", "suspended-clock"
    if remote is not None and remote > REMOTE_WINDOW_C:
        return "REMOTE_ATTEMPT_LATE", "remote-attempt"
    if off_rota:
        return "RESPONSE_TARGET", "revision-split"
    return "RESPONSE_TARGET", "core-response"


def evidence_refs(row, finding_type, corrupt):
    """Two carrier citation: the governing paging record, then the carrier that settles
    the figure the finding rests on."""
    cert = row["certificate"]
    if finding_type in ("HANDBACK_DOCUMENT_CONFLICT", "CERTIFICATE_OVERRIDE") \
            and cert is not None:
        second = cert["certificate_ref"]
    elif finding_type == "TELEMETRY_TOTAL_MISMATCH" and corrupt:
        second = corrupt["block_ref"]
    elif finding_type == "PARTS_WAIT_UNSUSPENDED" and row["parts_ref"]:
        second = row["parts_ref"]
    elif finding_type == "REMOTE_ATTEMPT_LATE" and row["remote_ref"]:
        second = row["remote_ref"]
    else:
        second = row["leg_ref"]
    return "%s;%s" % (row["paging_ref"], second)


def finding_set(incidents, notion, relied):
    corrupt_map = corrupt_block_refs(notion, incidents)
    off_rota = off_rota_refs(incidents)
    findings = []
    for ref in sorted(incidents):
        row = incidents[ref]
        revision, rows = exceedances(row, relied)
        for kind, allowance, actual, excess, conflicts, parts, remote in rows:
            corrupt = corrupt_map.get(ref)
            if kind == "ACKNOWLEDGEMENT_DELAY":
                finding_type, partition = "ACKNOWLEDGEMENT_DELAY", "core-response"
            else:
                finding_type, partition = classify(row, conflicts, parts, remote,
                                                   revision, corrupt, ref in off_rota)
            findings.append({
                "engineer_id": row["engineer_id"],
                "engineer_name": row["engineer_name"],
                "incident_ref": ref,
                "finding_type": finding_type,
                "revision": REVISIONS[revision]["label"],
                "allowance_minutes": allowance,
                "actual_minutes": actual,
                "excess_minutes": excess,
                "partition": partition,
                "evidence_refs": evidence_refs(row, finding_type, corrupt),
            })
    findings.sort(key=lambda f: (f["incident_ref"], f["finding_type"]))
    return findings


def register_index(notion):
    properties = notion.get("properties", {})
    out = {}
    for page in pages_in(notion, DB_REGISTER):
        props = properties.get(page["id"], {})
        out[value_of(props, "EngineerId")] = {
            "engineer_name": value_of(props, "EngineerName"),
            "mail_address": value_of(props, "MailAddress"),
            "audit_scope": value_of(props, "AuditScope"),
            "page_id": page["id"],
        }
    return out


def notice_set(findings, notion):
    register = register_index(notion)
    grouped = {}
    for finding in findings:
        grouped.setdefault(finding["engineer_id"], []).append(finding)
    out = []
    for engineer_id in sorted(grouped):
        rows = sorted(grouped[engineer_id],
                      key=lambda f: (f["incident_ref"], f["finding_type"]))
        entry = register.get(engineer_id, {})
        out.append({
            "engineer_id": engineer_id,
            "engineer_name": entry.get("engineer_name"),
            "to_address": entry.get("mail_address"),
            "subject": NOTICE_SUBJECT % engineer_id,
            "body_lines": [NOTICE_LINE % (f["incident_ref"], f["finding_type"],
                                          f["allowance_minutes"], f["actual_minutes"],
                                          f["excess_minutes"]) for f in rows],
            "finding_count": len(rows),
        })
    return out


def annotation_set(notion, notified):
    properties = notion.get("properties", {})
    out = []
    for page in pages_in(notion, DB_REPORTS):
        props = properties.get(page["id"], {})
        if str(value_of(props, "SignatureStatus", "")).strip().lower() != "signed":
            continue
        engineer_id = value_of(props, "EngineerId")
        if engineer_id not in notified:
            continue
        out.append({
            "report_ref": value_of(props, "ReportRef"),
            "service_desk_ref": value_of(props, "ServiceDeskRef"),
            "incident_ref": value_of(props, "IncidentRef"),
            "engineer_id": engineer_id,
            "annotation_line": ANNOTATION_LINE % engineer_id,
            "index_page": page["id"],
        })
    out.sort(key=lambda a: a["report_ref"])
    return out


DECISIVE_TRIGGER_FIELDS = ("DeclaredHandbackDepotLocal", "LoggedWaitMinutes",
                           "FirstAttemptMinutesAfterDispatch")


CARRIER_REFERENCE_FIELDS = {DB_CERTS: "CertificateRef", DB_PARTS: "WaitRef",
                            DB_REMOTE: "AttemptRef"}


def carrier_owners(notion):
    properties = notion.get("properties", {})
    out = {}
    for database_id, reference_field in sorted(CARRIER_REFERENCE_FIELDS.items()):
        for page in pages_in(notion, database_id):
            props = properties.get(page["id"], {})
            out[page["id"]] = (value_of(props, "IncidentRef"),
                               value_of(props, reference_field))
    return out


def correction_set(pre, post, applied, notion):
    """A correction is owed for every finding the trigger replay moved between the set the
    audit raised before any record moved and the set the settled world carries. Response
    figures that moved, and findings the replay withdrew, each owe one entry; a trigger
    that moved no finding owes nothing."""
    owners = carrier_owners(notion)
    moved = {}
    for change in applied:
        owner = owners.get(change["page"])
        if owner is None or change["field"] not in DECISIVE_TRIGGER_FIELDS:
            continue
        moved[owner[0]] = dict(change, record_ref=owner[1])

    def grouped(rows):
        out = {}
        for finding in rows:
            out.setdefault(finding["incident_ref"], []).append(finding)
        return out

    before, after = grouped(pre), grouped(post)
    out = []
    for ref in sorted(set(before) | set(after)):
        old_rows = before.get(ref, [])
        new_rows = after.get(ref, [])
        if old_rows == new_rows:
            continue
        old = old_rows[0] if old_rows else None
        new = new_rows[0] if new_rows else None
        anchor = old if old is not None else new
        if anchor is None:
            continue
        change = moved.get(ref, {})
        out.append({
            "incident_ref": ref,
            "finding_type": anchor["finding_type"],
            "settled_finding_type": None if new is None else new["finding_type"],
            "engineer_id": anchor["engineer_id"],
            "disposition": "withdrawn" if new is None
                           else ("raised" if old is None else "refigured"),
            "trigger": change.get("trigger"),
            "record_ref": change.get("record_ref",
                                     anchor["evidence_refs"].split(";")[-1]),
            "field_changed": change.get("field"),
            "old_value": change.get("old_value"),
            "new_value": change.get("new_value"),
            "old_excess_minutes": None if old is None else old["excess_minutes"],
            "new_excess_minutes": None if new is None else new["excess_minutes"],
            "reason": "the record the finding rested on moved after the audit relied on it",
        })
    return out


def recompute(world_dir):
    world = load_world(world_dir)
    notion = world["LightNotion"]
    monday = world["LightMonday"]
    with open(os.path.join(world_dir, "_LightNotion.rule.json"), encoding="utf-8") as fh:
        rule = json.load(fh)

    facts = load_media_facts()
    pre_incidents = read_incidents(notion, monday, facts)
    findings_pre = finding_set(pre_incidents, notion, relied=False)

    applied = apply_triggers(notion, rule)
    incidents = read_incidents(notion, monday, facts)
    for ref, row in incidents.items():
        source = pre_incidents[ref]
        row["parts_wait_relied"] = source["parts_wait_minutes"]
        row["remote_relied"] = source["remote_minutes"]

    findings = finding_set(incidents, notion, relied=True)
    findings_post = finding_set(incidents, notion, relied=False)
    corrections = correction_set(findings_pre, findings_post, applied, notion)

    notices = notice_set(findings, notion)
    notified = {n["engineer_id"] for n in notices}
    annotations = annotation_set(notion, notified)

    totals = {
        "FindingCount": len(findings),
        "TotalExcessMinutes": sum(f["excess_minutes"] for f in findings),
        "EngineersAffected": len(notified),
    }
    partitions, types, revisions = {}, {}, {}
    for finding in findings:
        partitions[finding["partition"]] = partitions.get(finding["partition"], 0) + 1
        types[finding["finding_type"]] = types.get(finding["finding_type"], 0) + 1
        revisions[finding["revision"]] = revisions.get(finding["revision"], 0) + 1

    return {
        "period": {"start": PERIOD_START, "end": PERIOD_END,
                   "revision_c_effective": "2026-10-19T00:00 depot local",
                   "clock_change": "2026-10-25T02:00+01:00 to 01:00+00:00"},
        "close_record": {
            "PeriodStart": PERIOD_START,
            "PeriodEnd": PERIOD_END,
            "FindingCount": totals["FindingCount"],
            "TotalExcessMinutes": totals["TotalExcessMinutes"],
            "EngineersAffected": totals["EngineersAffected"],
            "CloseState": "CLOSED",
        },
        "ticket_lines": [
            "RESPONSE-SUMMARY findings=%d" % totals["FindingCount"],
            "RESPONSE-SUMMARY excess-minutes=%d" % totals["TotalExcessMinutes"],
            "RESPONSE-SUMMARY engineers-notified=%d" % totals["EngineersAffected"],
        ],
        "totals": totals,
        "by_partition": dict(sorted(partitions.items())),
        "by_type": dict(sorted(types.items())),
        "by_revision": dict(sorted(revisions.items())),
        "weighted_positive": sum(PARTITION_WEIGHT[f["partition"]] for f in findings),
        "findings": findings,
        "notices": notices,
        "annotations": annotations,
        "corrections": corrections,
        "applied_changes": applied,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="recompute")
    ap.add_argument("--world-data",
                    default=os.environ.get("COMPLEXMCP_WORLD_DATA", "/world_data"))
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    truth = recompute(args.world_data)
    if args.summary:
        print("findings            %d" % truth["totals"]["FindingCount"])
        print("total excess mins   %d" % truth["totals"]["TotalExcessMinutes"])
        print("engineers affected  %d" % truth["totals"]["EngineersAffected"])
        print("notices             %d" % len(truth["notices"]))
        print("annotations         %d" % len(truth["annotations"]))
        print("corrections         %d" % len(truth["corrections"]))
        print("by type             %s" % truth["by_type"])
        print("by partition        %s" % truth["by_partition"])
        print("by revision         %s" % truth["by_revision"])
        print("weighted positive   %d" % truth["weighted_positive"])
        print("ticket lines        %s" % " | ".join(truth["ticket_lines"]))
        return 0
    json.dump(truth, sys.stdout, indent=1, sort_keys=True, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
