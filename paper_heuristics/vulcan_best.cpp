// EVOLVE-BLOCK START

// RANK: score regions (higher = better)
store_cfg.add_listeners(r_has_spot, {vulcan::listeners::object::EWMA({0.25})});
store_cfg.add_listeners(r_last_visit_tick, {vulcan::listeners::object::RollingWindow(1)});

rank_config.set_scoring_fn([=](const vulcan::feature_store& fs, int64_t obj_id) -> double {
    int64_t lv = fs.get_latest(r_last_visit_tick, obj_id);
    if (lv <= 0) return 55.0; // Exploration bonus
    
    double ewma = fs.get_ewma(r_has_spot, obj_id, 0.25);
    double base = ewma * 100.0;
    
    // Small boost for stale info (grows with staleness, capped)
    double staleness_boost = (lv > 10) ? 10.0 : (lv > 5) ? 5.0 : 0.0;
    
    return base + staleness_boost;
});

// VALUE: decide action (0=CHANGE_REGION, 1=SPOT, 2=ON_DEMAND)
store_cfg.add_listeners(v_elapsed, {vulcan::listeners::global::RollingWindow(1)});
store_cfg.add_listeners(v_progress, {vulcan::listeners::global::RollingWindow(1)});
store_cfg.add_listeners(v_has_spot, {vulcan::listeners::global::RollingWindow(1)});
store_cfg.add_listeners(v_last_cluster_type, {vulcan::listeners::global::RollingWindow(2)});

value_config.set_value_fn([=](const vulcan::feature_store& fs) -> double {
    double t = fs.get_latest(v_elapsed);
    double p = fs.get_latest(v_progress);
    int64_t hs = fs.get_latest(v_has_spot);
    
    double work_left = DURATION - p;
    if (work_left <= 1e-9) return SPOT;
    
    double time_left = DEADLINE - t;
    if (time_left <= 0) return ON_DEMAND;
    
    // Standard tick-aligned calculation
    int left_ticks = (int)(time_left / GAP);
    int need_ticks = (int)((work_left + RESTART_OVERHEAD) / GAP + 0.999);
    
    // Critical threshold
    if (need_ticks >= left_ticks) return ON_DEMAND;
    
    // Prefer SPOT when available
    if (hs) return SPOT;
    
    int margin = left_ticks - need_ticks;
    double pr = p / DURATION;
    
    // Light thrashing prevention: don't switch immediately after switching
    int64_t last_type = fs.get_latest(v_last_cluster_type);
    bool just_switched = (last_type == 0);
    
    // Progressive exploration with thrashing guard
    if (pr < 0.3 && margin >= 3 && !just_switched) return CHANGE_REGION;
    if (pr < 0.7 && margin >= 4 && !just_switched) return CHANGE_REGION;
    if (margin >= 5 && !just_switched) return CHANGE_REGION;
    
    // Allow immediate re-exploration if margin is very large
    if (margin >= 6) return CHANGE_REGION;
    
    return ON_DEMAND;
});

// EVOLVE-BLOCK END