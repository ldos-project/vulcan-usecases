// Fixed scaffolding for the multi-region RANK + VALUE policies.
// The heuristic block from OpenEvolve is copied to LLMCode.h at build
// time. libvulcan calls configure_rank and configure_value separately,
// passing a shared store_config. configure_rank stashes its arguments
// and configure_value drives the whole evolve block against both configs.

#include "vulcan.h"
#include <algorithm>
#include <cmath>
#include <cstdint>

#define CHANGE_REGION 0
#define SPOT          1
#define ON_DEMAND     2

#define DEADLINE         fs.get_latest(v_deadline)
#define DURATION         fs.get_latest(v_duration)
#define RESTART_OVERHEAD fs.get_latest(v_restart_overhead)
#define GAP              fs.get_latest(v_gap)
#define NUM_REGIONS      fs.get_latest(v_num_regions)

static vulcan::store_config* s_store_cfg;
static vulcan::rank_config*  s_rank_cfg;

extern "C" void vulcan_configure_rank(vulcan::feature_registry& /*registry*/,
                                      vulcan::store_config& store_cfg,
                                      vulcan::rank_config& rank_config)
{
    s_store_cfg = &store_cfg;
    s_rank_cfg  = &rank_config;
}

extern "C" void vulcan_configure_value(vulcan::feature_registry& registry,
                                       vulcan::store_config& /*store_cfg_arg*/,
                                       vulcan::value_config& value_config)
{
    vulcan::store_config& store_cfg = *s_store_cfg;
    vulcan::rank_config&  rank_config = *s_rank_cfg;

    auto r_has_spot        = registry.object.lookup_i64("has_spot");
    auto r_last_visit_tick = registry.object.lookup_i64("last_visit_tick");

    rank_config.set_comparator(vulcan::max);
    rank_config.set_sorting_function(vulcan::rank::FullSort);

    auto v_elapsed           = registry.global.lookup_f64("elapsed");
    auto v_progress          = registry.global.lookup_f64("progress");
    auto v_has_spot          = registry.global.lookup_i64("current_has_spot");
    auto v_last_cluster_type = registry.global.lookup_i64("last_cluster_type");
    auto v_num_regions       = registry.global.lookup_i64("num_regions");
    auto v_deadline          = registry.global.lookup_f64("deadline");
    auto v_duration          = registry.global.lookup_f64("duration");
    auto v_restart_overhead  = registry.global.lookup_f64("restart_overhead");
    auto v_gap               = registry.global.lookup_f64("gap_seconds");

    store_cfg.add_listeners(v_deadline,         {vulcan::listeners::global::RollingWindow(1)});
    store_cfg.add_listeners(v_duration,         {vulcan::listeners::global::RollingWindow(1)});
    store_cfg.add_listeners(v_restart_overhead, {vulcan::listeners::global::RollingWindow(1)});
    store_cfg.add_listeners(v_gap,              {vulcan::listeners::global::RollingWindow(1)});
    store_cfg.add_listeners(v_num_regions,      {vulcan::listeners::global::RollingWindow(1)});

    #include "LLMCode.h"
}
