#!/usr/bin/env python3
"""Measure memory and time of `Rules.inject_and_validate_rules`, as the OTLP provider calls it.

`OtlpProvider.rules` does, per relation and query type:

    rules = Rules(query_type, topology)
    result = rules.inject_and_validate_rules(requirer.rules.<query_type>, requirer.metadata)

This script does exactly that on a rules file, twice in one process (cold diskcache, then
warm), and prints wall time, spawned cos-tool processes and peak memory.

Usage (from the repo root; cos-tool is resolved as cos-tool-<arch> relative to CWD):

    python scripts/bench_validate.py --generate-apps 200 --out /tmp/rules.yaml   # synthetic data
    PYTHONPATH=src python scripts/bench_validate.py /tmp/rules.yaml              # working tree

To compare with older code, point PYTHONPATH at an exported copy of it:

    git archive <ref> src | tar -x -C /tmp/old && PYTHONPATH=/tmp/old/src python scripts/bench_validate.py ...

RULES is {"groups": [...]} (YAML or JSON), i.e. the decompressed `rules.promql` databag value.

Columns:
    py_peak   peak RSS of this process during the call (MiB, excludes loading the file)
    py_base   RSS right before the call, i.e. the loaded rules (MiB)
    cos_peak  RSS of the largest cos-tool process (MiB, RUSAGE_CHILDREN)
    spawns    cos-tool processes started (transform + validate)
    groups    groups kept / groups given
"""

import argparse
import copy
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# What the requirer publishes as `metadata` (JujuTopology.as_dict()).
METADATA = {
    "model": "bench-model",
    "model_uuid": "a2c1e559-c8e7-4053-8044-a2c1e5591c7f",
    "application": "bench-app",
    "unit": "bench-app/0",
    "charm_name": "bench-charm",
}


def status_mib(field: str) -> float:
    """Read a `kB` field (VmRSS, VmHWM) of /proc/self/status in MiB."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) / 1024
    raise KeyError(field)


def generate(apps: int, out: str) -> None:
    import yaml

    groups = [
        {
            "name": f"app{a}_g{g}_rules",
            "rules": [
                {
                    "alert": f"Alert{r}",
                    "expr": (
                        f'sum(rate(http_requests_total{{job="app{a}",handler="/h{r}"}}[5m]))'
                        f" by (instance) > {r * 10 + 1} and on(instance) up{{job=\"app{a}\"}} == 1"
                    ),
                    "for": "5m",
                    "labels": {"severity": "critical"},
                    "annotations": {"summary": "x" * 60},
                }
                for r in range(5)
            ],
        }
        for a in range(apps)
        for g in range(15)
    ]
    Path(out).write_text(yaml.dump({"groups": groups}))
    print(f"wrote {out}: {len(groups)} groups, {Path(out).stat().st_size / 2**20:.1f} MiB")


def bench(rules_path: str, query_type: str, cache_dir: Optional[str]) -> None:
    import yaml

    import cosl.cos_tool as cos_tool
    from cosl.juju_topology import JujuTopology
    from cosl.rules import Rules

    print(f"cosl: {cos_tool.__file__}")
    with open(rules_path) as f:
        rules = yaml.load(f, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    n_groups = len(rules["groups"])
    print(f"rules: {rules_path} ({Path(rules_path).stat().st_size / 2**20:.1f} MiB, {n_groups} groups)")

    if cache_dir is None:
        cache_dir = tempfile.mkdtemp(prefix="bench-cache-")
    print(f"cache: {cache_dir}")
    cos_tool.configure_cache(cache_dir)

    spawns = 0
    cos_peak_kib = 0
    real_run = subprocess.run

    def counting_run(cmd, *args, **kwargs):
        # RUSAGE_CHILDREN is useless here: a forked child starts with its parent's peak RSS,
        # so it reports the (large) Python process. GNU time reports the exec'd cos-tool alone.
        nonlocal spawns, cos_peak_kib
        spawns += 1
        with tempfile.NamedTemporaryFile("r") as out:
            try:
                return real_run(["/usr/bin/time", "-f", "%M", "-o", out.name, *cmd], *args, **kwargs)
            finally:
                lines = out.read().strip().splitlines()
                if lines and lines[-1].isdigit():
                    cos_peak_kib = max(cos_peak_kib, int(lines[-1]))

    cos_tool.subprocess.run = counting_run  # type: ignore[assignment]

    topology = JujuTopology.from_dict(METADATA)
    if Rules(query_type, topology).tool.path is None:  # type: ignore[arg-type]
        sys.exit("cos-tool binary not found: run from the dir containing cos-tool-<arch>")

    print(f"{'run':5} {'wall(s)':>9} {'py_peak':>9} {'py_base':>9} {'cos_peak':>9} {'spawns':>7}  groups  errmsg")
    for run in ("cold", "warm"):
        # Fresh input per run, as each reconcile loads it anew from the databag.
        data = copy.deepcopy(rules)
        spawns = 0
        cos_peak_kib = 0
        base = status_mib("VmRSS")
        Path("/proc/self/clear_refs").write_text("5")  # reset VmHWM to the current RSS
        t0 = time.perf_counter()
        result = Rules(query_type, topology).inject_and_validate_rules(data, dict(METADATA))  # type: ignore[arg-type]
        wall = time.perf_counter() - t0
        children = cos_peak_kib / 1024
        kept = len(result.rules.get("groups", []))
        print(
            f"{run:5} {wall:9.2f} {status_mib('VmHWM'):8.0f}M {base:8.0f}M {children:8.0f}M "
            f"{spawns:7d}  {kept}/{n_groups}  {(result.errmsg or '')[:80]}"
        )
        del data, result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("rules", nargs="?", help="rules file ({'groups': [...]}, YAML or JSON)")
    p.add_argument("--query-type", default="promql", choices=["promql", "logql"])
    p.add_argument(
        "--cache-dir",
        help="diskcache dir to use and keep between runs (default: a new temp dir each run, "
        "so every run starts cold). The first run is only cold if this dir is empty.",
    )
    p.add_argument("--generate-apps", type=int, help="write a synthetic rules file and exit")
    p.add_argument("--out", help="output path for --generate-apps")
    args = p.parse_args()

    if args.generate_apps:
        if not args.out:
            p.error("--generate-apps needs --out")
        generate(args.generate_apps, args.out)
    elif args.rules:
        bench(args.rules, args.query_type, args.cache_dir)
    else:
        p.error("rules file required")


if __name__ == "__main__":
    main()
