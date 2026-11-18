"""Keldford HGV WT-7 world generator.

Run from this file's parent directory (environment/):

    PYTHONDONTWRITEBYTECODE=1 python3 \\
        --no-dev python -m generator --root .

The world is a pure function of the world seed and the slot generation-input digest. The
seed arrives as COMPLEXMCP_SEED (the same variable the vendored light-servers platform
reads, default 7319) or --seed; the digest arrives as FORGE_SLOT_INPUT_DIGEST or
--input-digest. Neither value is written into any emitted byte.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import emit
import wt7


def resolve_inputs(argv):
    ap = argparse.ArgumentParser(prog="generator", add_help=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--seed", default=os.environ.get("COMPLEXMCP_SEED", "7319"))
    ap.add_argument("--input-digest",
                    default=os.environ.get("FORGE_SLOT_INPUT_DIGEST", "forge-slot-1"))
    ap.add_argument("--report", action="store_true")
    return ap.parse_args(argv)


def build(seed: str, input_digest: str) -> dict:
    digest = wt7.world_digest("%s:%s" % (seed, input_digest))
    salt = int(digest[:8], 16)
    people = wt7.build_people()
    duties = wt7.build_duties(people)
    wt7.apply_plants(duties)

    benign = emit.extra_cert_gap_duties(duties, 25)
    unsigned = emit.unsigned_gap_duties(duties)

    replacement = next(d for d in duties
                       if d["driver_index"] == 11 and "DAILY_DRIVING" in d["planted"]
                       and not d["gap"])
    replacement["pre_change"] = {
        "DrivingMinutes": replacement["drive_min"],
        "OtherWorkMinutes": replacement["other_work_min"],
    }
    replacement["drive_min"] += 37
    replacement["other_work_min"] -= 37

    findings = wt7.reference_findings(duties)
    reg = emit.build_registry(people, duties, findings)
    reg["salt"] = salt
    reg["benign_certs"] = benign
    reg["unsigned"] = unsigned
    reg["replacement_duty"] = replacement
    reg["injection_roster_duty_ref"] = reg["finding_duty_refs"][11]
    return reg


def verify(reg) -> None:
    duties, findings = reg["duties"], reg["findings"]
    assert len(duties) == 1180, len(duties)
    assert sum(1 for d in duties if not d["gap"]) == 1150
    assert sum(1 for d in duties if d["gap"]) == 30
    assert len(reg["cert_duties"]) + len(reg["benign_certs"]) == 28
    assert len(reg["unsigned"]) == 2
    assert sum(1 for d in duties if d["night_kind"] == "clock-change") == 6
    assert sum(1 for d in duties if d.get("spans_change")) == 6
    assert sum(1 for d in duties if d.get("unit_keyed_early")) == 1
    assert sum(1 for d in duties if d.get("fixed_offset_control")) == 1
    assert 36 <= len(findings) <= 40, len(findings)
    control = next(d for d in duties if d.get("fixed_offset_control"))
    assert not wt7.find_duty_exceedances(control)
    decoy_ids = {d["driver_id"] for d in reg["people"]["decoys"]}
    agency_ids = {d["driver_id"] for d in reg["people"]["agency"]}
    owners = {f["driver_id"] for f in findings}
    assert not owners & decoy_ids
    assert not owners & agency_ids
    assert len({f["finding_type"] for f in findings}) == 8
    assert sum(1 for f in findings if f["partition"] == "clock-change") >= 3


def report(reg) -> str:
    import collections
    findings = reg["findings"]
    types = collections.Counter(f["finding_type"] for f in findings)
    parts = collections.Counter(f["partition"] for f in findings)
    editions = collections.Counter(f["edition"] for f in findings)
    lines = [
        "reference findings: %d" % len(findings),
        "total excess minutes: %d" % sum(f["excess_minutes"] for f in findings),
        "drivers affected: %d" % len({f["driver_id"] for f in findings}),
        "by type: %s" % dict(sorted(types.items())),
        "by partition: %s" % dict(sorted(parts.items())),
        "by edition: %s" % dict(sorted(editions.items())),
        "weighted positive: %d" % sum(wt7.PARTITION_WEIGHT[f["partition"]] for f in findings),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    args = resolve_inputs(sys.argv[1:] if argv is None else argv)
    reg = build(str(args.seed), str(args.input_digest))
    verify(reg)
    overlays = emit.emit(os.path.abspath(args.root), reg)
    print("emitted %d overlays into %s" % (len(overlays) + 2, args.root))
    print(report(reg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
