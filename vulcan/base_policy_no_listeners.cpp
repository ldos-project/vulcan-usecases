// EVOLVE-BLOCK START
config.set_value_fn([=](const vulcan::feature_store& fs) -> double {
    double  t   = fs.get_latest(elapsed);
    double  p   = fs.get_latest(progress);
    int64_t hs  = fs.get_latest(has_spot);
    int64_t lct = fs.get_latest(last_cluster_type);

    double work_left = DURATION - p;
    if (work_left <= 1e-9) return NONE;

    int64_t left_ticks = std::max<int64_t>(
        0, static_cast<int64_t>(std::floor((DEADLINE - t) / GAP)));
    int64_t need1d = static_cast<int64_t>(std::ceil((work_left + RESTART_OVERHEAD) / GAP));
    int64_t need2d = static_cast<int64_t>(std::ceil((work_left + 2.0 * RESTART_OVERHEAD) / GAP));

    if (need1d >= left_ticks) return ON_DEMAND;
    if (need2d >= left_ticks) {
        if (lct == SPOT && hs) return SPOT;
        return ON_DEMAND;
    }
    return hs ? SPOT : NONE;
});
// EVOLVE-BLOCK END
