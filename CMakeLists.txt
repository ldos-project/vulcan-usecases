cmake_minimum_required(VERSION 3.12)

# Set the project name
project(VulcanEvolveCacheSim)

# #######################################
# find dependency #
# #######################################
set(LIBCACHE_SIM_DIR "${CMAKE_SOURCE_DIR}/libcachesim")
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${LIBCACHE_SIM_DIR}/cmake/Modules/")

set(CMAKE_BUILD_TYPE Debug)

# Find GLib using pkg-config
find_package(GLib "2.40" REQUIRED)
include_directories(${GLib_INCLUDE_DIRS})
message(STATUS "glib found? ${GLib_FOUND}, lib = ${GLib_LIBRARY}, header = ${GLib_INCLUDE_DIRS}")

find_package(ZSTD)
# https://stackoverflow.com/questions/61377055/cannot-find-gflags-gflags-h-while-building-library-osx/61379123#61379123
include_directories(${ZSTD_INCLUDE_DIR})
if ("${ZSTD_LIBRARIES}" STREQUAL "") 
    message(FATAL_ERROR "zstd not found")
endif()

# Include libCacheSim headers
include_directories(${CMAKE_SOURCE_DIR}/libcachesim/libCacheSim/include)
# include_directories(libCacheSim)

# Add the subdirectory containing libCacheSim
set(BUILD_SHARED_LIBS ON CACHE BOOL "Build shared libs" FORCE)

set(ENABLE_LRB OFF CACHE BOOL "Enable LRB algorithm" FORCE)
set(ENABLE_GLCACHE OFF CACHE BOOL "Enable GLCache algorithm" FORCE)

add_subdirectory(libcachesim)
set_target_properties(libCacheSim_shared PROPERTIES OUTPUT_NAME "CacheSim")

# The main executable to run
add_executable(run_algo.o src/run_algo.cpp)
target_link_libraries(run_algo.o libCacheSim_shared cache_lib_c traceReader_lib m ${GLib_LIBRARY} ${ZSTD_LIBRARIES})
target_compile_options(run_algo.o PRIVATE -Wall -Wextra -Wshadow -Wpedantic)

add_executable(get_footprint.o src/get_footprint.cpp)
target_link_libraries(get_footprint.o libCacheSim_shared cache_lib_c traceReader_lib m ${GLib_LIBRARY} ${ZSTD_LIBRARIES})
target_compile_options(get_footprint.o PRIVATE -Wall -Wextra -Wshadow -Wpedantic)

add_executable(run_baselines.o src/run_baselines.cpp)
target_link_libraries(run_baselines.o libCacheSim_shared cache_lib_c traceReader_lib m ${GLib_LIBRARY} ${ZSTD_LIBRARIES})
target_compile_options(run_baselines.o PRIVATE -Wall -Wextra -Wshadow -Wpedantic)

# Other executables removed because they do not exist

add_custom_target(run_install_libcachesim
    COMMAND ${CMAKE_COMMAND} -E echo "Running install_libcachesim.sh"
    COMMAND bash ${CMAKE_SOURCE_DIR}/libcachesim/scripts/install_libcachesim.sh
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)