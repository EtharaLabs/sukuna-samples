"""Task-local faults for the crew audit, installed into the Notion server process through sitecustomize.

Three deterministic faults on LightNotion.query_database, read from the task's world data
(_faults.json); without that file nothing is installed:

- rate limit: the Nth query in a session fails once with a rate-limit error and a retry interval;
- authorization: queries on the archive actuals database are refused; get_page still serves its records;
- truncation: the roster page that covers a fixed row index is cut at that row and reports no further page.
"""
from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys

TARGETS = {"notion", "software.LightNotion.notion"}


def _faults() -> dict:
    d = os.environ.get("COMPLEXMCP_WORLD_DATA", "").strip()
    path = os.path.join(d, "_faults.json") if d else ""
    if path and os.path.isfile(path):
        with open(path) as fh:
            return json.load(fh)
    return {}


def _patch(module) -> None:
    cls = getattr(module, "NotionSession", None)
    faults = _faults()
    if cls is None or not faults or getattr(cls, "_faults_installed", False):
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
