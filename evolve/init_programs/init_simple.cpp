state->config.add_listeners(state->accesses, { vulcan::listeners::object::EWMA({0.6667}) });

auto scoring_fn = [](const vulcan::feature_store& fs, int64_t obj_id) -> double {
    return fs.get_ewma(state->accesses, obj_id, 0.6667);
};