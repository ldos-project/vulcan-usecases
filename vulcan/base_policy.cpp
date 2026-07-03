// EVOLVE-BLOCK START

// ============================================================
// RANK policy: score each region by desirability (higher = better)
// Only the current region gets updated each tick; other regions
// retain stale listener state (natural caching).
// ============================================================
store_cfg.add_listeners(r_has_spot,        {vulcan::listeners::object::RollingWindow(10),
                                              vulcan::listeners::object::RollingCount(10),
                                              vulcan::listeners::object::EWMA({0.1})});
store_cfg.add_listeners(r_last_visit_tick, {vulcan::listeners::object::RollingWindow(1)});

rank_config.set_scoring_fn([=](const vulcan::feature_store& fs, int64_t obj_id) -> double {
    double ewma = fs.get_ewma(r_has_spot, obj_id, 0.1);
    int64_t last_visit = fs.get_latest(r_last_visit_tick, obj_id);

    // Unvisited regions (last_visit == 0) get high exploration bonus
    if (last_visit <= 0) return 200.0;

    return ewma * 100.0;
});

// ============================================================
// VALUE policy: decide action (0=CHANGE_REGION, 1=SPOT, 2=ON_DEMAND)
// Matches initial_program.py logic: linear progress check.
// ============================================================
store_cfg.add_listeners(v_elapsed,           {vulcan::listeners::global::RollingWindow(1)});
store_cfg.add_listeners(v_progress,          {vulcan::listeners::global::RollingWindow(1)});
store_cfg.add_listeners(v_has_spot,          {vulcan::listeners::global::RollingWindow(1)});
store_cfg.add_listeners(v_last_cluster_type, {vulcan::listeners::global::RollingWindow(1)});

value_config.set_value_fn([=](const vulcan::feature_store& fs) -> double {
    double  t   = fs.get_latest(v_elapsed);
    double  p   = fs.get_latest(v_progress);
    int64_t hs  = fs.get_latest(v_has_spot);

    double work_left = DURATION - p;
    if (work_left <= 1e-9) return CHANGE_REGION;

    // Linear progress check (matches initial_program.py _is_behind_schedule)
    double required_progress = (t > 0 && DEADLINE > t) ? t * DURATION / DEADLINE : 0.0;
    bool behind = p < required_progress;

    if (behind) {
        if (hs) return SPOT;
        return ON_DEMAND;
    }

    if (hs) return SPOT;
    return CHANGE_REGION;
});

// EVOLVE-BLOCK END
