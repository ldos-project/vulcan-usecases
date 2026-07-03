# EVOLVE-BLOCK-START

import configargparse
import logging
import typing

from sky_spot.strategies.multi_strategy import MultiRegionStrategy
from sky_spot.utils import ClusterType

if typing.TYPE_CHECKING:
    from sky_spot import env, task

logger = logging.getLogger(__name__)

class EvolutionaryStrategy(MultiRegionStrategy):
    """
    Refined strategy with balanced urgency calculation and efficient exploration.
    """
    NAME = 'evolutionary_refined'

    def __init__(self, args: configargparse.Namespace):
        super().__init__(args)
        self.initialized: bool = False
        self.region_cache: typing.Dict[int, typing.Dict[str, typing.Any]] = {}
        self.last_spot_region: int = -1
        self.exploration_counter: int = 0

    def reset(self, env: 'env.Env', task: 'task.Task'):
        super().reset(env, task)
        num_regions = self.env.get_num_regions()
        for i in range(num_regions):
            self.region_cache[i] = {'has_spot': None, 'last_checked': -1, 'spot_count': 0, 'total_checks': 0}
        self.initialized = True
        self.last_spot_region = -1
        self.exploration_counter = 0

    def _calculate_urgency(self) -> float:
        """Calculate urgency with balanced approach."""
        remaining_work = self.task_duration - sum(self.task_done_time)
        remaining_time = self.deadline - self.env.elapsed_seconds
        
        if remaining_time <= 0:
            return 999.0
        
        # Work pressure: how much time per unit of work
        work_rate = remaining_work / remaining_time
        
        # Schedule tracking: are we behind linear progress?
        progress = sum(self.task_done_time) / self.task_duration if self.task_duration > 0 else 0
        time_ratio = self.env.elapsed_seconds / self.deadline if self.deadline > 0 else 0
        schedule_lag = max(time_ratio - progress, 0)
        
        # Combine with moderate weighting
        return work_rate * 0.15 + schedule_lag

    def _get_region_reliability(self, region_idx: int) -> float:
        """Calculate reliability score for a region."""
        cache = self.region_cache[region_idx]
        if cache['total_checks'] == 0:
            return 0.5  # Unknown
        return cache['spot_count'] / cache['total_checks']

    def _select_exploration_target(self, current: int, num_regions: int) -> int:
        """Select best region for exploration using reliability and staleness."""
        best_idx = -1
        best_score = -999
        now = self.env.elapsed_seconds
        
        for i in range(num_regions):
            if i == current:
                continue
            
            cache = self.region_cache[i]
            reliability = self._get_region_reliability(i)
            
            # Score based on multiple factors
            if cache['has_spot'] is True:
                # Known good region - high priority
                score = 80 + reliability * 20
            elif cache['has_spot'] is None:
                # Unknown region - medium-high priority
                score = 50
            else:
                # Known no-spot - lower priority, but consider staleness
                staleness = now - cache['last_checked']
                score = min(staleness / 120, 30)
            
            if score > best_score:
                best_score = score
                best_idx = i
        
        return best_idx if best_idx >= 0 else (current + 1) % num_regions

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        if not self.initialized or self.task_done:
            return ClusterType.NONE

        current_region = self.env.get_current_region()
        num_regions = self.env.get_num_regions()

        # Update cache with current information
        cache = self.region_cache[current_region]
        cache['has_spot'] = has_spot
        cache['last_checked'] = self.env.elapsed_seconds
        cache['total_checks'] += 1
        
        if has_spot:
            cache['spot_count'] += 1
            self.last_spot_region = current_region

        urgency = self._calculate_urgency()
        
        # CRITICAL: Approaching deadline, must guarantee progress
        if urgency >= 0.4:
            if has_spot:
                return ClusterType.SPOT
            return ClusterType.ON_DEMAND
        
        # HIGH: Behind schedule, limited exploration
        if urgency >= 0.2:
            if has_spot:
                self.exploration_counter = 0
                return ClusterType.SPOT
            
            # Try last known good region once
            if (self.last_spot_region >= 0 and 
                self.last_spot_region != current_region and 
                self.exploration_counter == 0):
                self.exploration_counter = 1
                self.env.switch_region(self.last_spot_region)
                return ClusterType.NONE
            
            self.exploration_counter = 0
            return ClusterType.ON_DEMAND
        
        # MODERATE: Balanced approach
        if urgency >= 0.08:
            if has_spot:
                self.exploration_counter = 0
                return ClusterType.SPOT
            
            # Allow 2 exploration ticks
            if self.exploration_counter < 2:
                self.exploration_counter += 1
                target = self._select_exploration_target(current_region, num_regions)
                self.env.switch_region(target)
                return ClusterType.NONE
            
            self.exploration_counter = 0
            return ClusterType.ON_DEMAND
        
        # LOW: Maximize cost savings through exploration
        if has_spot:
            self.exploration_counter = 0
            return ClusterType.SPOT
        
        # Explore intelligently for better spot options
        target = self._select_exploration_target(current_region, num_regions)
        self.env.switch_region(target)
        return ClusterType.NONE

# EVOLVE-BLOCK-END