cmake_minimum_required(VERSION 3.15...3.30)
project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_tickbuffer feature/cpp/bindings.cpp)
target_include_directories(_tickbuffer PRIVATE feature/cpp)

if(MSVC)
  target_compile_options(_tickbuffer PRIVATE /W4)
else()
  target_compile_options(_tickbuffer PRIVATE -Wall -Wextra -O3)
endif()

install(TARGETS _tickbuffer LIBRARY DESTINATION feature)
