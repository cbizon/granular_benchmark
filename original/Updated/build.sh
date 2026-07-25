#!/bin/bash
# Build the resurrected granular sim on modern toolchains (arm64/x86_64, clang or gcc).
cd "$(dirname "$0")"
g++ -w -O2 -o grains clist.c fel.c plist.c collide.c detect.c stat.c cell.cc files.c xmain.c -lm
echo "built ./grains"
