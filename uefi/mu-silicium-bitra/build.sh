#!/bin/sh
# Build Mu-Silicium bitra UEFI from source (no sudo, shim for libuuid headers)
. "$(dirname "$(readlink -f "${BASH_SOURCE:-$0}")")/env.sh" || exit 1
S=$MU_DIR
export PATH=$CLANG_DIR:$S/venv/bin:$PATH
export CPATH=$S/shim/include LIBRARY_PATH=$S/shim/lib
cd $S/mu
python3 build_uefi.py -d bitra ${EXTRA} > $S/build.log 2>&1
echo "exit $?" >> $S/build.log
