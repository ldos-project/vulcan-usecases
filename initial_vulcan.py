"""
Multi-region CBL strategy using two composed libvulcan policies:
  VALUE: urgency features -> action (CHANGE_REGION/SPOT/ON_DEMAND)
  RANK: cached per-region observations -> preference ordering
  Only current region is observed each tick (no oracle).
  RANK fires only when VALUE returns CHANGE_REGION.
"""

import ctypes
import os
import sys

from sky_spot.strategies.multi_strategy import MultiRegionStrategy
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
    os.path.join(_REPO_ROOT, "vulcan", "cbl_multi_policy.so"),
)

ctypes.CDLL(_LIBVULCAN_SO, mode=ctypes.RTLD_GLOBAL)
if _VULCAN_PY not in sys.path:
    sys.path.insert(0, _VULCAN_PY)

import vulcan

_CLUSTER_TO_INT = {
    ClusterType.NONE: 0,
    ClusterType.SPOT: 1,
    ClusterType.ON_DEMAND: 2,
}


class VulcanMultiRegionStrategy(MultiRegionStrategy):
    NAME = "vulcan_multi_seed"

    def __init__(self, args):
        super().__init__(args)
        self._rank_policy = None
        self._value_policy = None
        self._plugin = None
        self._handles = {}

    def _build_policies(self):
        reg = vulcan.FeatureRegistry()
        ro = reg.object_features
        vg = reg.global_features
        h = {
            "has_spot_r":        ro.declare_i64("has_spot", "1 if spot available when last visited"),
            "last_visit_tick":   ro.declare_i64("last_visit_tick", "tick number of last visit"),
            "elapsed":           vg.declare_f64("elapsed", "seconds since task start"),
            "deadline":          vg.declare_f64("deadline", "absolute deadline in seconds"),
            "duration":          vg.declare_f64("duration", "total work needed in seconds"),
            "progress":          vg.declare_f64("progress", "seconds of work completed"),
            "restart_overhead":  vg.declare_f64("restart_overhead", "switch penalty in seconds"),
            "gap_seconds":       vg.declare_f64("gap_seconds", "tick size in seconds"),
            "has_spot_v":        vg.declare_i64("current_has_spot", "1 if spot available in current region"),
            "last_cluster_type": vg.declare_i64("last_cluster_type", "0=NONE, 1=SPOT, 2=ON_DEMAND"),
            "num_regions":       vg.declare_i64("num_regions", "total number of regions"),
        }

        rank_cfg = vulcan.RankConfig()
        rank_cfg.set_information(
            "Score each cloud region by desirability for running a spot instance. "
            "Higher score = more desirable. Only the current region is observed each tick; "
            "other regions retain stale cached values. Use historical availability patterns "
            "and staleness to balance exploitation vs exploration."
        )

        value_cfg = vulcan.ValueConfig()
        value_cfg.set_information(
            "Choose an action per tick. Return 0 for CHANGE_REGION (switch to "
            "a different region), 1 for SPOT, 2 for ON_DEMAND. Minimize cost "
            "while guaranteeing the job finishes before deadline."
        )

        store_cfg = vulcan.StoreConfig()
        self._plugin = vulcan.load_policy(_POLICY_SO)
        self._plugin.configure_rank(reg, store_cfg, rank_cfg)
        self._plugin.configure_value(reg, store_cfg, value_cfg)

        store = vulcan.make_shared_feature_store(reg, store_cfg)
        rank_policy = vulcan.instantiate_rank_policy(reg, rank_cfg, store)
        value_policy = vulcan.instantiate_value_policy(reg, value_cfg, store)
        return rank_policy, value_policy, h

    def reset(self, env, task):
        super().reset(env, task)

        self._rank_policy, self._value_policy, self._handles = self._build_policies()

        for i in range(self.env.get_num_regions()):
            self._rank_policy.add_object(i)

        store = self._value_policy.feature_store
        h = self._handles
        store.update(h["deadline"],         float(self.deadline))
        store.update(h["duration"],         float(self.task_duration))
        store.update(h["restart_overhead"], float(self.restart_overhead))
        store.update(h["gap_seconds"],      float(self.env.gap_seconds))
        store.update(h["num_regions"],      self.env.get_num_regions())

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        current_region = self.env.get_current_region()
        tick = self.env.tick

        store = self._value_policy.feature_store
        h = self._handles
        store.update(h["has_spot_r"], current_region, 1 if has_spot else 0)
        store.update(h["last_visit_tick"], current_region, tick)
        store.update(h["elapsed"],           float(self.env.elapsed_seconds))
        store.update(h["progress"],          float(sum(self.task_done_time)))
        store.update(h["has_spot_v"],        1 if has_spot else 0)
        store.update(h["last_cluster_type"], _CLUSTER_TO_INT.get(last_cluster_type, 0))

        decision = int(round(self._value_policy.decide()))

        if decision == 1:
            return ClusterType.SPOT
        elif decision == 2:
            return ClusterType.ON_DEMAND
        else:
            ranked = self._rank_policy.rank_candidates()
            for region_id, _score in ranked:
                if region_id != current_region:
                    self.env.switch_region(region_id)
                    break
            return ClusterType.NONE
