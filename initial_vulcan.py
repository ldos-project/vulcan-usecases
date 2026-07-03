# EVOLVE-BLOCK START
"""
CBL strategy that delegates per-tick decisions to a libvulcan VALUE policy.

The C++ EVOLVE block (vulcan/cbl_policy.cpp) returns a scalar in {0, 1, 2}:
  0 -> ClusterType.NONE, 1 -> ClusterType.SPOT, 2 -> ClusterType.ON_DEMAND
"""

import ctypes
import os
import sys

from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType


def _locate_repo_root() -> str:
    env = os.environ.get("CBL_REPO_ROOT")
    if env:
        return os.path.abspath(env)
    return os.path.dirname(os.path.abspath(__file__))


_REPO_ROOT = _locate_repo_root()
_VULCAN_BUILD = os.path.join(_REPO_ROOT, "third_party", "libvulcan", "build")
_VULCAN_PY = os.path.join(_VULCAN_BUILD, "python")
_LIBVULCAN_SO = os.path.join(_VULCAN_BUILD, "libvulcan.so")
_POLICY_SO = os.environ.get(
    "CBL_POLICY_SO",
    os.path.join(_REPO_ROOT, "vulcan", "cbl_policy.so"),
)

# Preload libvulcan with RTLD_GLOBAL so the plugin .so can find its symbols
# without relying on LD_LIBRARY_PATH.
ctypes.CDLL(_LIBVULCAN_SO, mode=ctypes.RTLD_GLOBAL)
if _VULCAN_PY not in sys.path:
    sys.path.insert(0, _VULCAN_PY)

import vulcan  # noqa: E402


_DECISION_TO_CLUSTER = {
    0: ClusterType.NONE,
    1: ClusterType.SPOT,
    2: ClusterType.ON_DEMAND,
}

_CLUSTER_TO_INT = {v: k for k, v in _DECISION_TO_CLUSTER.items()}


class VulcanStrategy(Strategy):
    NAME = "vulcan_seed"

    def __init__(self, args):
        super().__init__(args)
        self._policy = None
        self._handles: dict = {}

    def _build_policy(self):
        reg = vulcan.FeatureRegistry()
        g = reg.global_features
        handles = {
            "elapsed":            g.declare_f64("elapsed", "seconds since task start"),
            "deadline":           g.declare_f64("deadline", "absolute deadline in seconds"),
            "duration":           g.declare_f64("duration", "total work needed in seconds"),
            "progress":           g.declare_f64("progress", "seconds of work completed"),
            "restart_overhead":   g.declare_f64("restart_overhead", "switch penalty d in seconds"),
            "gap_seconds":        g.declare_f64("gap_seconds", "tick size in seconds"),
            "has_spot":           g.declare_i64("has_spot", "1 if SPOT is available this tick, else 0"),
            "last_cluster_type":  g.declare_i64("last_cluster_type", "0=NONE, 1=SPOT, 2=ON_DEMAND"),
        }
        cfg = vulcan.ValueConfig()
        cfg.set_information(
            "Choose a cluster type per tick. Return 0 for NONE (wait), "
            "1 for SPOT, 2 for ON_DEMAND. Minimize cost while guaranteeing "
            "the job finishes before deadline. Switching instance types wastes "
            "`restart_overhead` seconds; equality against safety lines is unsafe."
        )
        plugin = vulcan.load_policy(_POLICY_SO)
        plugin.configure_value(reg, cfg)
        policy = vulcan.instantiate_value_policy(reg, cfg)
        return policy, handles

    def reset(self, env, task):
        super().reset(env, task)
        self._policy, self._handles = self._build_policy()
        store = self._policy.feature_store
        h = self._handles
        store.update(h["deadline"],         float(self.deadline))
        store.update(h["duration"],         float(self.task_duration))
        store.update(h["restart_overhead"], float(self.restart_overhead))
        store.update(h["gap_seconds"],      float(self.env.gap_seconds))

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        store = self._policy.feature_store
        h = self._handles
        store.update(h["elapsed"],          float(self.env.elapsed_seconds))
        store.update(h["progress"],         float(sum(self.task_done_time)))
        store.update(h["has_spot"],         1 if has_spot else 0)
        store.update(h["last_cluster_type"], _CLUSTER_TO_INT.get(last_cluster_type, 0))

        raw = int(round(self._policy.decide()))
        return _DECISION_TO_CLUSTER.get(raw, ClusterType.NONE)

    @classmethod
    def _from_args(cls, parser):
        args, _ = parser.parse_known_args()
        return cls(args)

# EVOLVE-BLOCK END
