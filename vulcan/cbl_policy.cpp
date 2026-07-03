// Fixed scaffolding for the Can't-Be-Late VALUE policy.
// The heuristic (listeners + value function) is in LLMCode.h,
// copied from the OpenEvolve-generated file at build time.
//
// Return encoding: NONE, SPOT, ON_DEMAND (macros defined below)

#include "vulcan.h"
#include <algorithm>
#include <cmath>
#include <cstdint>

#define NONE      0
#define SPOT      1
#define ON_DEMAND 2

#define DEADLINE         fs.get_latest(deadline)
#define DURATION         fs.get_latest(duration)
#define RESTART_OVERHEAD fs.get_latest(restart_overhead)
#define GAP              fs.get_latest(gap)


extern "C" void vulcan_configure_value(vulcan::feature_registry& registry,
                                       vulcan::value_config& config) {
    // Per-tick observations
    auto elapsed          = registry.global.lookup_f64("elapsed");
    auto progress         = registry.global.lookup_f64("progress");
    auto has_spot         = registry.global.lookup_i64("has_spot");
    auto last_cluster_type = registry.global.lookup_i64("last_cluster_type");

    // Constants (fixed for the entire task)
    auto deadline         = registry.global.lookup_f64("deadline");
    auto duration         = registry.global.lookup_f64("duration");
    auto restart_overhead = registry.global.lookup_f64("restart_overhead");
    auto gap              = registry.global.lookup_f64("gap_seconds");

    config.add_listeners(deadline,         {vulcan::listeners::global::RollingWindow(1)});
    config.add_listeners(duration,         {vulcan::listeners::global::RollingWindow(1)});
    config.add_listeners(restart_overhead, {vulcan::listeners::global::RollingWindow(1)});
    config.add_listeners(gap,              {vulcan::listeners::global::RollingWindow(1)});

    #include "LLMCode.h"
}
