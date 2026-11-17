"""python -m generator --out DIR --world-seed N --task-seed N"""
import argparse
import json
from pathlib import Path

from . import emit, world

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--world-seed", type=int, required=True)
ap.add_argument("--task-seed", type=int, required=True)
a = ap.parse_args()
plan = world.build(a.world_seed, a.task_seed)
emit.write(plan, Path(a.out))
t = plan["truth"]
print(json.dumps({"implicated_batches": len(t["batches"]), "blends": len(t["blends"]), "held": len(t["held"]),
                  "recall_customers": len(t["recall"]), "recall_pallets": sum(map(len, t["recall"].values())), "mass_balance": t["mass_balance"]}))
