"""Task-local faults for the response audit, installed into the server processes through sitecustomize.

Every fault is deterministic and read from the task's world data (_faults.json); without that
file nothing is installed.

Three faults land on LightNotion.query_database:

- rate limit: the Nth query in a session fails once with a rate-limit error and a retry interval;
- authorization: queries on the archive actuals database are refused; get_page still serves its records;
- truncation: the roster page that covers a fixed row index is cut at that row and reports no further page.

One fault lands on a whole app rather than one call, and models a vendor withdrawing a tool part
way through a long job:

- retirement: the app's world tools are counted as they serve. Once the count passes the
  configured threshold, every further call to the named tool answers with a withdrawal notice
  instead of records. A second tool on the same app has served the same records from the start
  and is left alone; the notice does not say which one it is, because finding it is the work.

The retirement counter is a module global, one entry per app. Each app runs as its own single
server process, so a process-wide count is a per-app count.
"""
from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys

NOTION_TARGETS = {"notion", "software.LightNotion.notion"}
MONDAY_TARGETS = {"monday", "software.LightMonday.monday"}
TARGETS = NOTION_TARGETS | MONDAY_TARGETS

NEVER_COUNTED = {"get_session_dict", "uuid"}

_served: dict = {}


def _faults() -> dict:
    d = os.environ.get("COMPLEXMCP_WORLD_DATA", "").strip()
    path = os.path.join(d, "_faults.json") if d else ""
    if path and os.path.isfile(path):
        with open(path) as fh:
            return json.load(fh)
    return {}


def _patch_notion(module, faults) -> None:
    cls = getattr(module, "NotionSession", None)
    if cls is None or getattr(cls, "_faults_installed", False):
        return
    orig = cls.query_database

    def query_database(self, database_id, filter_status=None, filter_assignee=None, sort_by=None, start_cursor=None, page_size=50):
        n = getattr(self, "_fault_queries", 0) + 1
        self._fault_queries = n
        rl = faults.get("rate_limit", {})
        if n == int(rl.get("call", 0)):
            return {"status": "failed", "output": rl["message"]}
        auth = faults.get("authorization", {})
        if database_id == auth.get("database"):
            return {"status": "failed", "output": auth["message"]}
        res = orig(self, database_id, filter_status, filter_assignee, sort_by, start_cursor, page_size)
        tr = faults.get("truncation", {})
        if database_id == tr.get("database") and res.get("status") == "ok" and not (filter_status or filter_assignee or sort_by):
            try:
                offset = int(start_cursor) if start_cursor else 0
            except (TypeError, ValueError):
                offset = 0
            total = sum(1 for p in self.pages if p["parent_type"] == "database" and p["parent_id"] == database_id and not p["archived"])
            cut = total - int(tr["rows_hidden"])
            out = res["output"]
            if offset <= cut < offset + len(out["results"]):
                out["results"] = out["results"][: cut - offset]
                out["next_cursor"] = None
                out["has_more"] = False
        return res

    cls.query_database = query_database
    cls._faults_installed = True


def _install_retirement(cls, app: str, plan: dict) -> None:
    """Count the app's world tools, then answer the retired one once the count is past its threshold.

    Every public method of the session class is wrapped, so the threshold is reached by any mix of
    calls rather than by repeating one tool. A wrapped method takes its call through *args and
    **kwargs: the platform has already validated the arguments by this point, and passing them
    straight through keeps a tool's own signature the only description of it that matters.
    """
    retired = plan.get("tool", "")
    after = int(plan.get("after_call", 0) or 0)
    notice = plan.get("message", "")
    if not retired or not hasattr(cls, retired) or after <= 0 or not notice:
        return
    _served.setdefault(app, 0)

    def wrap(name, func):
        def counted(self, *args, **kwargs):
            _served[app] = _served.get(app, 0) + 1
            if name == retired and _served[app] > after:
                return {"status": "failed", "output": notice}
            return func(self, *args, **kwargs)

        counted.__name__ = name
        return counted

    for name in sorted(vars(cls)):
        if name.startswith("_") or name in NEVER_COUNTED:
            continue
        func = vars(cls)[name]
        if callable(func):
            setattr(cls, name, wrap(name, func))


def _patch_monday(module, faults) -> None:
    cls = getattr(module, "MondaySession", None)
    plan = faults.get("retirement", {})
    if cls is None or getattr(cls, "_faults_installed", False):
        return
    if plan.get("app") == "LightMonday":
        _install_retirement(cls, "LightMonday", plan)
    cls._faults_installed = True


def _patch(module) -> None:
    faults = _faults()
    if not faults:
        return
    if getattr(module, "NotionSession", None) is not None:
        _patch_notion(module, faults)
    if getattr(module, "MondaySession", None) is not None:
        _patch_monday(module, faults)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name not in TARGETS:
            return None
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return spec
        loader = spec.loader
        orig_exec = loader.exec_module

        def exec_module(module):
            orig_exec(module)
            _patch(module)
        loader.exec_module = exec_module
        return spec


def install() -> None:
    for name in TARGETS:
        if name in sys.modules:
            _patch(sys.modules[name])
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
