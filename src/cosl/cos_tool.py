# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""COS Tool."""

import functools
import logging
import os
import platform
import re
import subprocess
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

import yaml
from diskcache import Cache  # pyright: ignore[reportMissingTypeStubs]
from typing_extensions import TypeVar

from .types import OfficialRuleFileFormat, QueryType

logger = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable[..., Any])

# Upper bound (in bytes) for the on-disk cos-tool result cache. cos-tool is invoked once
# per alert expression and its (deterministic) results are memoized to avoid the dominant
# cost: the subprocess spawn (~tens of ms) on every reconcile. Once the size limit is
# exceeded, the least-recently-*used* entries are evicted (see ``_EXEC_CACHE_EVICTION``),
# so the cache never grows unbounded while staying "hot" for the expressions actually in
# use. Entries are short strings, so this comfortably holds the distinct expressions of a
# large (hundreds of apps) aggregation deployment with room to grow.
_EXEC_CACHE_SIZE_LIMIT = 256 * 1024 * 1024  # 256 MiB

# Evict the least-recently-*used* entries (not diskcache's default least-recently-stored),
# so entries that keep being looked up survive and only genuinely stale ones are dropped.
_EXEC_CACHE_EVICTION = "least-recently-used"

# Default on-disk location for the cache when ``configure_cache`` is not called. A fixed,
# shared path (rather than a random temp dir) means all processes reuse the same cache, so
# even callers that never configure a persistent directory get cross-process reuse for the
# lifetime of this directory. Juju serialises hook execution per unit, so there is no
# concurrent writer. Note ``/tmp`` typically does not survive a reboot / pod recreation;
# use ``configure_cache`` with real persistent storage when that matters.
_DEFAULT_CACHE_DIR = "/tmp/cosl-cos-tool"  # noqa: S108

# The cache is opened lazily (see ``_get_cache``) rather than at import, so importing this
# module has no filesystem side effects (no directory creation, no failure on a read-only
# or permission-restricted ``/tmp``). Only the target directory is held at module scope.
_cache_dir: str = _DEFAULT_CACHE_DIR
_exec_cache: Optional[Cache] = None


def _get_cache() -> Cache:
    """Return the process-wide cache, opening it at ``_cache_dir`` on first use."""
    global _exec_cache
    if _exec_cache is None:
        _exec_cache = Cache(
            directory=_cache_dir,
            size_limit=_EXEC_CACHE_SIZE_LIMIT,
            eviction_policy=_EXEC_CACHE_EVICTION,
        )
    return _exec_cache


def configure_cache(cache_dir: Optional[Union[str, Path]]) -> None:
    """Point the cos-tool result cache at a specific directory.

    By default the cache lives at a fixed shared path (``/tmp/cosl-cos-tool``), which gives
    cross-process reuse but does not survive a reboot or pod recreation. Charms reconcile on
    every Juju event (a fresh process each time), so point this at a persistent directory
    (e.g. a charm's persistent storage mount) to carry the cache across process invocations
    reliably.

    Passing ``None`` reverts to the default shared location. The cache is (re)opened lazily
    on next use, so this never creates directories eagerly.

    Args:
        cache_dir: directory in which to store the cache, or ``None`` for the default.
    """
    global _cache_dir, _exec_cache
    _cache_dir = str(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
    if _exec_cache is not None:
        _exec_cache.close()
    _exec_cache = None  # reopened lazily at _cache_dir on next use


@functools.lru_cache(maxsize=None)
def _cosl_version() -> str:
    """Return the installed ``cosl`` version (or ``"0"`` if it can't be determined)."""
    try:
        return version("cosl")
    except PackageNotFoundError:
        return "0"


@functools.lru_cache(maxsize=None)
def _binary_fingerprint(path: str) -> str:
    """Return a cheap fingerprint of the cos-tool binary at ``path``.

    Uses size + mtime rather than a content hash: it detects a replaced binary while
    staying effectively free (one ``stat``, no multi-MB read), memoized per path.
    """
    try:
        st = os.stat(path)
    except OSError:
        return "missing"
    return f"{st.st_size}:{st.st_mtime_ns}"


def _fingerprint(binary_path: str) -> str:
    """Return a fingerprint invalidating the cache when results could change.

    Combines the ``cosl`` version and the binary's size+mtime, so a library upgrade or a
    replaced cos-tool binary yields new cache keys instead of serving stale output.
    """
    return f"cosl={_cosl_version()};bin={_binary_fingerprint(binary_path)}"


def _exec(cmd: List[str], cache_key: Optional[Tuple[str, ...]] = None) -> str:
    """Run a cos-tool command, memoizing its (deterministic) output.

    Args:
        cmd: the cos-tool command to run on a cache miss.
        cache_key: a deterministic key identifying the invocation. Defaults to ``cmd``;
            pass an explicit key for commands that reference a nondeterministic path
            (e.g. the tempfile used by ``validate_alert_rules``), so the cache still hits.
    """
    cache = _get_cache()
    # Prefix the key with a fingerprint (cosl version + binary size/mtime) so a library
    # upgrade or a replaced cos-tool binary invalidates entries automatically, rather than
    # silently returning output computed by a previous binary. cmd[0] is the binary path.
    key = (_fingerprint(cmd[0]),) + (tuple(cache_key) if cache_key is not None else tuple(cmd))
    # diskcache ships no type stubs, so ``get``/``set`` are untyped; we only ever store
    # ``str`` under these keys, so cast the retrieved value back to ``str``.
    cached = cast(Optional[str], cache.get(key))  # pyright: ignore[reportUnknownMemberType]
    if cached is not None:
        return cached
    result = subprocess.run(
        list(cmd), check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    output = result.stdout.decode("utf-8").strip()
    cache.set(key, output)  # pyright: ignore[reportUnknownMemberType]
    return output


def ensure_querytype(func: _F) -> _F:
    """A small decorator to ensure that query type is specified."""

    def wrapper(self: "CosTool", *args: Any, **kwargs: Any) -> Any:
        if not self.query_type and not kwargs.get("query_type", None):
            raise TypeError(
                "Either a default query type or a per-method query type must be used for `CosTool`!"
            )
        return func(self, *args, **kwargs)

    wrapper.__doc__ = func.__doc__
    return wrapper  # type: ignore


class CosTool:
    """Uses cos-tool to inject label matchers into alert rule expressions and validate rules.

    Args:
        default_query_type: an optional querytype to use for all invocations of this class, if
          not specified per-method. Either :default_query_type: or per-method :query_type:
          **must** be used, or a :TypeError: will be raised.
    """

    _path = None
    _disabled = False
    query_type: Union[QueryType, None] = None

    def __init__(self, default_query_type: Optional[QueryType] = None):
        self.query_type = default_query_type

    @property
    def path(self):
        """Lazy lookup of the path of cos-tool."""
        if self._disabled:
            return None
        if not self._path:
            self._path = self._get_tool_path()
            if not self._path:
                logger.debug("Skipping injection of juju topology as label matchers")
                self._disabled = True
        return self._path

    @ensure_querytype
    def apply_label_matchers(
        self, rules: OfficialRuleFileFormat, query_type: Optional[QueryType] = None
    ) -> OfficialRuleFileFormat:
        """Will apply label matchers to the expression of all alerts in all supplied groups."""
        query_type = query_type or self.query_type
        if not self.path:
            return rules
        for group in rules.get("groups", []):
            rules_in_group = group.get("rules", [])
            for rule in rules_in_group:
                topology = {}
                # if the user for some reason has provided juju_unit, we'll need to honor it
                # in most cases, however, this will be empty
                labels = rule.get("labels", {})
                for label in [
                    "juju_model",
                    "juju_model_uuid",
                    "juju_application",
                    "juju_charm",
                    "juju_unit",
                ]:
                    if label in labels:
                        topology[label] = labels[label]

                rule["expr"] = self.inject_label_matchers(rule["expr"], topology, query_type)  # type: ignore
        return rules

    @ensure_querytype
    def validate_alert_rules(
        self, rules: OfficialRuleFileFormat, query_type: Optional[QueryType] = None
    ) -> Tuple[bool, str]:
        """Will validate correctness of alert rules, returning a boolean and any errors."""
        query_type = query_type or self.query_type
        if not self.path:
            logger.debug("`cos-tool` unavailable. Not validating alert correctness.")
            return True, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            rule_path = Path(tmpdir + "/validate_rule.yaml")

            # Smash "our" rules format into what upstream actually uses for Loki,
            # which is more like:
            #
            # groups:
            #   - name: foo
            #     rules:
            #       - alert: SomeAlert
            #         expr: up
            #       - alert: OtherAlert
            #         expr: up
            if query_type == "logql":
                transformed_rules = OfficialRuleFileFormat(groups=[])
                for rule in rules.get("groups", []):
                    transformed_rules.get("groups", []).append(rule)

                rules = transformed_rules

            rules_yaml = yaml.dump(rules)
            rule_path.write_text(rules_yaml)

            args = [str(self.path), "--format", query_type, "validate", str(rule_path)]
            # The tempfile path is nondeterministic, so it must not be part of the cache
            # key or validation would never be memoized. Key on the rule *content*
            # instead: validation is a pure function of the binary, format and rules.
            cache_key = (
                str(self.path),
                "--format",
                query_type,
                "validate",
                "--content",
                rules_yaml,
            )
            # noinspection PyBroadException
            try:
                self._exec(args, cache_key=cache_key)  # type: ignore
                return True, ""
            except subprocess.CalledProcessError as e:
                logger.debug("Validating the rules failed: %s", e.output.decode("utf-8"))
                return False, ", ".join(
                    [
                        line
                        for line in e.output.decode("utf-8").splitlines()
                        if "error validating" in line
                    ]
                )

    @ensure_querytype
    def inject_label_matchers(
        self,
        expression: str,
        topology: Dict[str, str],
        query_type: Optional[QueryType] = None,
        dashboard_variable: Optional[bool] = False,
    ) -> str:
        """Add label matchers to an expression."""
        query_type = query_type or self.query_type

        if not topology:
            return expression
        if not self.path:
            logger.debug("`cos-tool` unavailable. Leaving expression unchanged: %s", expression)
            return expression
        args = [str(self.path), "--format", query_type, "transform"]

        value_tmpl = r"${}" if dashboard_variable else "{}"

        variable_topology = {k: value_tmpl.format(topology[k]) for k in topology.keys()}
        args.extend(
            [
                "--label-matcher={}={}".format(key, value)
                for key, value in variable_topology.items()
            ]
        )

        # Pass a leading "--" so expressions with a negation or subtraction aren't interpreted as
        # flags
        args.extend(["--", "{}".format(expression)])
        # noinspection PyBroadException
        try:
            return (
                re.sub(r'="\$juju', r'=~"$juju', self._exec(args))  # type: ignore
                if dashboard_variable
                else self._exec(args)  # type: ignore
            )
        except subprocess.CalledProcessError as e:
            logger.debug('Applying the expression failed: "%s", falling back to the original', e)
            return expression

    def _get_tool_path(self) -> Optional[Path]:
        arch = platform.machine()
        arch = "amd64" if arch == "x86_64" else arch
        res = "cos-tool-{}".format(arch)
        try:
            path = Path(res).resolve(strict=True)
            return path
        except (FileNotFoundError, OSError):
            logger.debug('Could not locate cos-tool at: "{}"'.format(res))
        return None

    def _exec(self, cmd: List[str], cache_key: Optional[Tuple[str, ...]] = None) -> str:
        # Delegate to the module-level, memoized worker. The result depends only on the
        # command inputs (not on instance state), so identical invocations across the
        # many short-lived CosTool instances created during rule processing are
        # deduplicated, avoiding redundant subprocess spawns.
        #
        # ``cache_key`` lets callers memoize on something other than ``cmd`` itself,
        # which matters for commands that reference a nondeterministic path (e.g. the
        # tempfile used by ``validate_alert_rules``): keying on the file path would
        # never hit, so those callers pass a content-derived key instead.
        return _exec(cmd, cache_key=cache_key)
