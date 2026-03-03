#include "util.h"

int main(int argc, char **argv) {
    const char *trace_path = argv[1];
    bool ignore_obj_size = false;
    if (argc == 3) {
        ignore_obj_size = true;
        std::string ignore_str = std::string(argv[3]);
        assert (ignore_str == "--ignore" && "To ignore object sizes from trace, pass 'ignore' as third argument; to consider them pass nothing.");
    }
    reader_t *reader = get_reader(trace_path, ignore_obj_size);

    std::string trace_print_name = reader->trace_path;
    std::string trace_path_str = std::string(trace_path);
    size_t last_slash = trace_path_str.rfind('/');
    if (last_slash != std::string::npos) {
        std::string prefix_to_remove = trace_path_str.substr(0, last_slash + 1);
        size_t pos = trace_print_name.find(prefix_to_remove);
        if (pos != std::string::npos) trace_print_name.replace(pos, prefix_to_remove.size(), "");
    }
    auto footprint = calculate_trace_footprint(reader);
    auto n_req = get_n_req(reader);
    printf("{\"trace\": \"%s\", \"footprint_mb\":%f, \"footprint_objs\": %ld, \"n_req\": %ld}\n", trace_print_name.c_str(), footprint.first/(1024.0 * 1024.0), footprint.second, n_req);
    close_trace(reader);
    return 0;
}