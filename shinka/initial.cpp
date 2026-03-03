// EVOLVE-BLOCK-START
config.add_listeners(f_last_access, {vulcan::listeners::object::RollingWindow(3)});
config.add_listeners(f_count, {vulcan::listeners::object::RollingWindow(3), vulcan::listeners::object::EWMA(0.1)});
config.add_listeners(f_size, {vulcan::listeners::object::RollingWindow(1), vulcan::listeners::object::PopulationPercentile()});
config.add_listeners(f_ghost, {vulcan::listeners::global::RollingCount(500)});

auto scoring_fn = [&](FS_REF fs, int64_t obj_id) -> double {
    // Recency: larger last_access = more recent = higher utility
    double last_access = static_cast<double>(fs.get_latest(f_last_access, obj_id));

    // Smoothed frequency — EWMA dampens bursty access patterns; higher = higher utility
    double freq = fs.get_ewma(f_count, obj_id) + 1.0;

    // Size relative to population median: prefer keeping small objects
    // (keeping small hot objects is more byte-efficient)
    double size_median = fs.get_percentile(f_size, 0.5);
    double size = static_cast<double>(fs.get_latest(f_size, obj_id));
    double size_factor = size / std::max(1.0, size_median);

    // Ghost bonus: object was evicted recently but re-requested — proven demand, keep it
    double ghost_count = static_cast<double>(fs.get_count(f_ghost, obj_id));
    double ghost_bonus = ghost_count * 50.0;

    // GDSF-style utility: keep recent, frequent, small objects; boost objects
    // with proven re-access demand. Higher return = higher utility = keep longer.
    return (last_access * freq / size_factor) + ghost_bonus;
};
config.set_scoring_fn(scoring_fn);

// EVOLVE-BLOCK-END
