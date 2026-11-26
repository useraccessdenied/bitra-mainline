#!/bin/sh
# Build Mu-Silicium bitra UEFI from source (no sudo, shim for libuuid headers)
S=/var/home/kapil/projects/bitra/mu-silicium
export PATH=/var/home/kapil/projects/bitra/android/roms/lineageos/a16/prebuilts/clang/host/linux-x86/clang-r563880c/bin:$S/venv/bin:$PATH
export CPATH=$S/shim/include LIBRARY_PATH=$S/shim/lib
cd $S/mu
python3 build_uefi.py -d bitra ${EXTRA} > $S/build.log 2>&1
echo "exit $?" >> $S/build.log
