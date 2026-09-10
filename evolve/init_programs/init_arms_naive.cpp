// Based on: https://github.com/DivyanshuSaxena/memory_tiering_search/blob/e9ad64d2abff9419b865502e821c061aa2eeb570/evolve/init.cpp

const int NUM_WINDOWS = 20; 

state->config.add_listeners(state->accesses, { vulcan::listeners::object::RollingWindow(NUM_WINDOWS) });

auto scoring_fn = [](const vulcan::feature_store& fs, int64_t obj_id) -> double {
    const float BIAS_RECENT = 0.731;
    const float BIAS_LONG   = 0.269;

    // For now using 1s and 10s horizons -- this can be updated.
    const float ALPHA_1S  = 0.6667;  // EWMA alpha for 1 sec horizon
    const float ALPHA_10S = 0.0952;  // EWMA alpha for 10 sec horizon

    float w_1s  = 0.0f;  // reconstructed EWMA for 1-second horizon
    float w_10s = 0.0f;  // reconstructed EWMA for 10-second horizon

    for (int i = 0; i < NUM_WINDOWS; i++) {
        uint16_t x = 0;
        x += fs.get_kth_recent(state->accesses, obj_id, NUM_WINDOWS - i);
        // Apply the EWMA update equations in chronological order
        w_1s  = (1.0f - ALPHA_1S)  * w_1s  + ALPHA_1S  * x;
        w_10s = (1.0f - ALPHA_10S) * w_10s + ALPHA_10S * x;
    }
    
    return BIAS_RECENT * w_1s + BIAS_LONG * w_10s;
};