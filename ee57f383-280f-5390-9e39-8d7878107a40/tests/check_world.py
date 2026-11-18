"""Build-time check that every app the world overlay names resolves to a served corpus."""
import os
import sys

sys.path.insert(0, "/tests")
os.environ["SUKUNA_RECOMPUTE"] = "/opt/truth/recompute.py"
os.environ["SUKUNA_WORLD_DATA"] = "/opt/truth/world_data"
os.environ["SUKUNA_SOFTWARE_DIR"] = "/opt/truth/software"
import test_output as t

rc = t._recompute_module()
served = t._served_world(rc, "/opt/truth/world_data")
overlay = rc.load_world("/opt/truth/world_data")
blind = [a for a in overlay if not a.startswith("_") and not t._corpus_world(a)]
if blind:
    raise SystemExit("no corpus resolved for %s; the guard baseline would stay blind" % blind)
print("served apps:", len([a for a in served if not a.startswith("_")]))
for app in ("LightOutlook", "LightSlack", "LightGoogleCalendar"):
    print(app, sorted(t._counts(served[app]).items()))
