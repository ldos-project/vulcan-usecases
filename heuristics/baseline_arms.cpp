#define ALPHA_1S 0.6667
#define ALPHA_10S 0.0952

f_config.add_listeners(f_accesses, { vulcan::listeners::object::EWMA({ALPHA_1S, ALPHA_10S}) });

auto scoring_fn = [](FS_REF fs, int64_t obj_id) -> double {
    double BIAS_RECENT = 0.731;
    double BIAS_LONG   = 0.269;

    // For now using 1s and 10s horizons -- this can be updated.
    double w_1s  = fs.get_ewma(f_accesses, obj_id, ALPHA_1S);  // reconstructed EWMA for 1-second horizon
    double w_10s = fs.get_ewma(f_accesses, obj_id, ALPHA_10S);  // reconstructed EWMA for 10-second horizon

    return BIAS_RECENT * w_1s + BIAS_LONG * w_10s;
};
