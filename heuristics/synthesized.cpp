// Vulcan-synthesized memory-tiering heuristic (paper Listing 4, "Vulcan-GUPS"):
// synthesized against the GUPS benchmark, then applied unchanged to every workload
// (the Fig. 9 generalization study).

f_config.add_listeners(f_accesses, {
    vulcan::listeners::object::EWMA({0.95, 0.35})
});

auto scoring_fn = [](FS_REF fs, int64_t obj_id) -> double {
    double fast = fs.get_ewma(f_accesses, obj_id, 0.95);
    double slow = fs.get_ewma(f_accesses, obj_id, 0.35);
    double accel = (slow > 0.001) ? (fast / slow) : 1.0;
    return fast * (1.0 + 0.55 * std::min(accel, 2.5));
};
