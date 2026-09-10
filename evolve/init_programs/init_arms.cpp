#define ALPHA_1S 0.6667
#define ALPHA_10S 0.0952

state->config.add_listeners(state->accesses, { vulcan::listeners::object::EWMA({ALPHA_1S, ALPHA_10S}) });

auto scoring_fn = [](const vulcan::feature_store& fs, int64_t obj_id) -> double {
    const float BIAS_RECENT = 0.731;
    const float BIAS_LONG   = 0.269;

    // For now using 1s and 10s horizons -- this can be updated.
    float w_1s  = fs.get_ewma(state->accesses, obj_id, ALPHA_1S);  // reconstructed EWMA for 1-second horizon
    float w_10s = fs.get_ewma(state->accesses, obj_id, ALPHA_10S);  // reconstructed EWMA for 10-second horizon

    return BIAS_RECENT * w_1s + BIAS_LONG * w_10s;
};