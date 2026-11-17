"""Safe nurse staffing standard SS-4, revisions 6 and 7: shift-length, extension, rest and rolling-hours rules.

Pure functions over resolved shifts. A resolved shift carries the evidence-adjusted actual times (the generator
resolves bleep-log voice notes, ward timesheet photographs and extension-authorisation scans before calling in
here), so the same code serves the generator, the oracle and the verifier. All instants are minutes since
2026-01-01T00:00Z. The trust keeps UK local time: BST (UTC+1) until 01:00 UTC on 25 October 2026, GMT after it.
A shift's ward assignments are the internal legs; a transfer from another site before the shift is the
positioning leg; post-shift handover is the post-flight allowance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
LOCAL_OFFSET = 60
GMT_FROM_UTC = None  # set below once to_min exists
AMENDMENT_LOCAL = "2026-10-15T00:00"
BLOCK_FIRST_DAY = "2026-10-01"
BLOCK_LAST_DAY = "2026-10-28"
POST_FLIGHT = 30
EDITIONS = ("Rev 6", "Rev 7")

# Report-time bands in local minutes after midnight, each with limits for 1-2, 3, 4, 5 and 6+ sectors.
BANDS = (
    ((360, 809), (780, 750, 720, 690, 660)),
    ((810, 839), (765, 735, 705, 675, 645)),
    ((840, 1049), (720, 690, 660, 630, 600)),
    ((300, 359), (720, 690, 660, 630, 600)),
)
NIGHT = (660, 630, 600, 570, 540)
EARLY_CUT_REV14 = 30
DISCRETION_MAX = {"Rev 6": 120, "Rev 7": 90}
HOME_REST_MIN, AWAY_REST_MIN = 660, 660
CUMULATIVE = (("HOURS_7D", 7, 3600), ("HOURS_14D", 14, 6600), ("HOURS_28D", 28, 11400))
HOME_STANDBY_SHARE = 0.25


def to_min(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int((dt - EPOCH).total_seconds() // 60)


def to_iso(m: int) -> str:
    return (EPOCH + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%MZ")


GMT_FROM_UTC = to_min("2026-10-25T01:00Z")


def offset(m: int) -> int:
    """UK local offset in minutes at UTC instant m: BST until the clocks go back, GMT after."""
    return LOCAL_OFFSET if m < GMT_FROM_UTC else 0


def local_day(m: int) -> str:
    return (EPOCH + timedelta(minutes=m + offset(m))).strftime("%Y-%m-%d")


def local_clock(m: int) -> int:
    t = EPOCH + timedelta(minutes=m + offset(m))
    return t.hour * 60 + t.minute


def local_to_utc(day: str, clock: int) -> int:
    """The UTC instant of local wall time ``clock`` minutes after midnight on ``day``."""
    wall = to_min(day + "T00:00Z") + clock
    return wall - LOCAL_OFFSET if wall - LOCAL_OFFSET < GMT_FROM_UTC else wall


AMENDMENT_UTC = local_to_utc(AMENDMENT_LOCAL[:10], 0)


def edition_at(m: int) -> str:
    return "Rev 7" if m >= AMENDMENT_UTC else "Rev 6"


def max_fdp(report: int, sectors: int, edition: str) -> int:
    clock = local_clock(report)
    row = NIGHT
    for (lo, hi), limits in BANDS:
        if lo <= clock <= hi:
            row = limits
            break
    idx = min(max(sectors, 2), 6) - 2
    limit = row[idx]
    if edition == "Rev 7" and 300 <= clock <= 359:
        limit -= EARLY_CUT_REV14
    return limit


@dataclass
class Duty:
    """One resolved duty. kind is SHIFT, ONSITE_CALL or HOME_CALL."""
    ref: str
    staff: str
    kind: str
    report: int
    end: int
    sectors: int = 0
    positioning: bool = False
    away: bool = False
    discretion_filed: bool = False
    evidence: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class Finding:
    staff: str
    key_ref: str
    limit_type: str
    edition: str
    limit_min: int
    actual_min: int
    excess_min: int
    evidence: tuple[str, ...] = ()
    partition: str = "core"
    source_refs: tuple[str, ...] = field(default=())

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.staff, self.key_ref, self.limit_type)


def duty_minutes(d: Duty) -> int:
    if d.kind == "SHIFT":
        return d.end + POST_FLIGHT - d.report
    if d.kind == "HOME_CALL":
        return int((d.end - d.report) * HOME_STANDBY_SHARE)
    return d.end - d.report


def fdp_findings(d: Duty) -> list[Finding]:
    if d.kind != "SHIFT":
        return []
    ed = edition_at(d.report)
    counted = d.sectors + (1 if d.positioning and ed == "Rev 7" else 0)
    limit = max_fdp(d.report, counted, ed)
    actual = d.end - d.report
    if actual <= limit:
        return []
    if d.discretion_filed:
        cap = limit + DISCRETION_MAX[ed]
        if actual <= cap:
            return []
        return [Finding(d.staff, d.ref, "EXTENSION", ed, cap, actual, actual - cap, d.evidence, source_refs=(d.ref,))]
    return [Finding(d.staff, d.ref, "SHIFT", ed, limit, actual, actual - limit, d.evidence, source_refs=(d.ref,))]


def rest_findings(prev: Duty, d: Duty) -> list[Finding]:
    if d.kind != "SHIFT" or prev.kind == "HOME_CALL":
        return []
    ed = edition_at(d.report)
    prev_len = duty_minutes(prev)
    need = max(prev_len, AWAY_REST_MIN if prev.away else HOME_REST_MIN)
    if ed == "Rev 7" and prev.kind == "SHIFT" and prev.discretion_filed:
        counted = prev.sectors + (1 if prev.positioning and edition_at(prev.report) == "Rev 7" else 0)
        ext = max(0, (prev.end - prev.report) - max_fdp(prev.report, counted, edition_at(prev.report)))
        need += ext
    rest = d.report - (prev.end + (POST_FLIGHT if prev.kind == "SHIFT" else 0))
    if rest >= need:
        return []
    ev = tuple(dict.fromkeys(prev.evidence + d.evidence))
    return [Finding(d.staff, d.ref, "REST", ed, need, rest, need - rest, ev, source_refs=(prev.ref, d.ref))]


def cumulative_findings(staff: str, duties: list[Duty]) -> list[Finding]:
    out: list[Finding] = []
    first = datetime.fromisoformat(BLOCK_FIRST_DAY)
    days = [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(28)]
    per_day: dict[str, list[Duty]] = {}
    for d in duties:
        per_day.setdefault(local_day(d.report), []).append(d)
    for limit_type, span, limit in CUMULATIVE:
        for day in days:
            end = datetime.fromisoformat(day)
            window = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(span)]
            members = [d for w in window for d in per_day.get(w, [])]
            total = sum(duty_minutes(d) for d in members)
            if total > limit:
                ev = tuple(dict.fromkeys(e for d in members for e in d.evidence))
                ed = edition_at(local_to_utc(day, 1439))
                out.append(Finding(staff, day, limit_type, ed, limit, total, total - limit, ev,
                                   source_refs=tuple(d.ref for d in members)))
                break
    return out


def audit(duties: list[Duty]) -> list[Finding]:
    """Every finding for the shifts given, one nurse at a time, inside the roster period."""
    by_staff: dict[str, list[Duty]] = {}
    for d in duties:
        by_staff.setdefault(d.staff, []).append(d)
    found: list[Finding] = []
    for staff, ds in sorted(by_staff.items()):
        ds.sort(key=lambda x: x.report)
        in_block = [d for d in ds if BLOCK_FIRST_DAY <= local_day(d.report) <= BLOCK_LAST_DAY]
        for d in in_block:
            found += fdp_findings(d)
        for prev, d in zip(ds, ds[1:]):
            if d in in_block:
                found += rest_findings(prev, d)
        found += cumulative_findings(staff, ds)
    return found


def assign_partitions(findings: list[Finding], duties: dict[str, Duty]) -> None:
    """Partition precedence: late, audio, image, edition, cumulative, rest, discretion, core."""
    for f in findings:
        tags = {t for r in f.source_refs for t in duties[r].tags}
        if f.limit_type.startswith("HOURS_"):
            tags = {t for t in tags if t in ("late", "audio")}
        for name in ("late", "audio", "image", "edition"):
            if name in tags:
                f.partition = name
                break
        else:
            if f.limit_type.startswith("HOURS_"):
                f.partition = "cumulative"
            elif f.limit_type == "REST":
                f.partition = "rest"
            elif f.limit_type == "EXTENSION" or "no_report" in tags:
                f.partition = "discretion"
            else:
                f.partition = "core"
