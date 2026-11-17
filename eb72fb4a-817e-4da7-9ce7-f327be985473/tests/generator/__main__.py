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
sizes = emit.write(world.build(a.world_seed, a.task_seed), Path(a.out))
print(json.dumps(sizes))
