// "Promote nothing" seed (paper Fig. 9 / §7.3): scores every page 0, so no page is
// ever ranked above another and ARMS performs no migrations -- the naive starting point
// the evolutionary search improves upon.
auto scoring_fn = [](FS_REF fs, int64_t obj_id) -> double {
    return 0.0;
};
