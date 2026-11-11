cmake_minimum_required(VERSION 3.22.1)
project(crashhandler C)

add_library(crashhandler SHARED native_crash_handler.c)

target_compile_options(crashhandler PRIVATE -O2 -Wall -fno-omit-frame-pointer -fvisibility=hidden)
target_link_libraries(crashhandler dl)
