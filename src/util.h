#include "../libcachesim/libCacheSim/include/libCacheSim.h"

#include <thread>
#include <string>
#include <unordered_set>

std::pair<long, long> calculate_trace_footprint(reader_t *reader) {
    reset_reader(reader);
    long footprint = 0;
    long long n_req = 0;
    request_t req;
    std::unordered_set<uint64_t> unique_objects;

    while (read_trace(reader, &req) == 0) {
        n_req++;
        auto [it, inserted] =  unique_objects.insert(req.obj_id);
        if(inserted) {
          footprint += req.obj_size;
          assert(req.obj_size > 0);
        }
    }
    reset_reader(reader); // Reset the reader to the beginning
    fprintf(stderr, "Trace footprint: %.3f MB (%.3fM objects) over %lld requests\n", footprint/(1024.0 * 1024.0), unique_objects.size()/1000000.0, n_req);
    return std::make_pair(footprint, unique_objects.size());
}

long long get_n_req(reader_t *reader) {
    reset_reader(reader);
    long long n_req = 0;
    request_t req;
    while (read_trace(reader, &req) == 0) n_req++; 
    reset_reader(reader); // Reset the reader to the beginning
    return n_req;
}

bool ends_with(const char *str, const char *suffix) {
    size_t len_str = strlen(str);
    size_t len_suffix = strlen(suffix);
    return len_str >= len_suffix && strcmp(str + len_str - len_suffix, suffix) == 0;
}

reader_t* get_reader(const char* trace_path, bool ignore_obj_size) {
    reader_init_param_t init_params = default_reader_init_params();
    if(ignore_obj_size) init_params.ignore_obj_size = true;
    
    if(ends_with(trace_path, ".csv")) return open_trace(trace_path, CSV_TRACE , &init_params);
    else if(ends_with(trace_path, ".zst")) return open_trace(trace_path, ORACLE_GENERAL_TRACE , &init_params);
    else {
        fprintf(stderr, "Unsupported trace format: %s\n", trace_path);
        assert(false);
    }
}