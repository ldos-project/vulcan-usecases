#include "util.h"

double cache_percentage = -1.0;
common_cache_params_t cc_params = default_common_cache_params();

void run_multiple_caches(reader_t *reader) {
  reset_reader(reader);

  auto start = std::chrono::high_resolution_clock::now();  
  const int NUM_CACHE_ALGORITHMS = 2;
  cache_t *caches[NUM_CACHE_ALGORITHMS] = {
      VulcanPQEvolve_init(cc_params, nullptr), 
      FIFO_init(cc_params, nullptr),
  };
  assert(NUM_CACHE_ALGORITHMS == sizeof(caches) / sizeof(caches[0]));
  cache_stat_t *result;
  result = simulate_with_multi_caches(
    reader, caches, NUM_CACHE_ALGORITHMS, nullptr, 0.0, 0,
    static_cast<int>(std::thread::hardware_concurrency()), false, false
  );
  
  auto end = std::chrono::high_resolution_clock::now();

  std::string trace_print_name = reader->trace_path;
  std::string trace_path_str = std::string(reader->trace_path);
  size_t last_slash = trace_path_str.rfind('/');
  if (last_slash != std::string::npos) {
      std::string prefix_to_remove = trace_path_str.substr(0, last_slash + 1);
      size_t pos = trace_print_name.find(prefix_to_remove);
      if (pos != std::string::npos) trace_print_name.replace(pos, prefix_to_remove.size(), "");
  }
  double duration_sec = std::chrono::duration<double>(end - start).count();

  for (int i = 0; i < NUM_CACHE_ALGORITHMS; ++i) {
    double miss_ratio      = (double)result[i].n_miss      / (double)result[i].n_req;
    double byte_miss_ratio = (double)result[i].n_miss_byte / (double)result[i].n_req_byte;

    printf(
        "{\"cache_name\":\"%s\","
        "\"trace_name\":\"%s\","
        "\"cache_size\":%lu,"
        "\"percent\":%lf,"
        "\"num_miss\":%lu,"
        "\"num_req\":%ld,"
        "\"miss_ratio\":%.6f,"
        "\"byte_miss_ratio\":%.6f,"
        "\"runtime_seconds\":%.6f}\n",
        result[i].cache_name,
        trace_print_name.c_str(),
        result[i].cache_size,
        cache_percentage,
        result[i].n_miss,
        result[i].n_req,
        miss_ratio,
        byte_miss_ratio,
        duration_sec
    );
  }

  free(result);
  for (int i = 0; i < NUM_CACHE_ALGORITHMS; i++) {
    caches[i]->cache_free(caches[i]);
  }
}

int main(int argc, char *argv[]) {
  assert(argc >= 2 && "./run_algo.o <trace_path> [--ignore] [--percent P | --size S]");
  const char *trace_path = argv[1];

  bool ignore_obj_size = false;
  bool has_percent = false;
  bool has_size = false;
  long absolute_size = -1;

  for(int i = 2; i < argc; i++) {
    std::string flag = argv[i];
    if(flag == "--ignore") {
        ignore_obj_size = true;
    } else if(flag == "--percent") {
        if(i + 1 >= argc) {
            fprintf(stderr, "Error: --percent requires a value\n");
            exit(1);
        }
        cache_percentage = std::stod(std::string(argv[++i]));
        has_percent = true;
    } else if(flag == "--size") {
        if(i + 1 >= argc) {
            fprintf(stderr, "Error: --size requires a value\n");
            exit(1);
        }
        absolute_size = std::stol(std::string(argv[++i]));
        has_size = true;
    } else {
        fprintf(stderr, "Unknown flag: %s\n", argv[i]);
        exit(1);
    }
  }

  if(has_percent == has_size) {
    fprintf(stderr, "Error: exactly one of --percent or --size must be specified\n");
    exit(1);
  }

  reader_t *reader = get_reader(trace_path, ignore_obj_size);

  if(has_size) {
    cc_params.cache_size = absolute_size;
  } else {
    if(ignore_obj_size) {
      long num_objects = calculate_trace_footprint(reader).second;
      cc_params.cache_size = cache_percentage * num_objects;
    } else {
      long trace_footprint_bytes = calculate_trace_footprint(reader).first;
      cc_params.cache_size = cache_percentage * trace_footprint_bytes;
    }
  }
  cc_params.hashpower = 16;
  
  run_multiple_caches(reader);
  close_trace(reader);
}