# Common settings for the HakiOS/Mu build scripts; sourced by them. Override any variable from the environment.
#   BITRA_ROOT  folder holding hakios/ and mu-silicium/ (found from this file's location, else ~/projects/bitra)
#   HAKIOS_DIR, MU_DIR   the HakiOS and Mu-Silicium working folders (default under BITRA_ROOT)
#   CLANG_DIR   directory of a recent clang (default: the AOSP clang in BITRA_ROOT/android if present, else the clang on PATH)
#   CMAKE_BIN, BUILD_TOOLS_BIN   optional extra tool directories (default: the AOSP prebuilts if present)
_src=$(readlink -f "${BASH_SOURCE:-$0}")
if [ -z "$BITRA_ROOT" ]; then
  for _c in "$(dirname "$_src")/../../.." "$HOME/projects/bitra"; do
    if [ -d "$_c/hakios" ] && [ -d "$_c/mu-silicium" ]; then BITRA_ROOT=$(cd "$_c" && pwd); break; fi
  done
fi
[ -n "$BITRA_ROOT" ] || { echo "env.sh: set BITRA_ROOT (folder with hakios/ and mu-silicium/)" >&2; return 1 2>/dev/null || exit 1; }
HAKIOS_DIR=${HAKIOS_DIR:-$BITRA_ROOT/hakios}
MU_DIR=${MU_DIR:-$BITRA_ROOT/mu-silicium}
_aosp=$BITRA_ROOT/android/roms/lineageos/a16/prebuilts
if [ -z "$CLANG_DIR" ]; then
  if [ -d "$_aosp/clang/host/linux-x86/clang-r563880c/bin" ]; then CLANG_DIR=$_aosp/clang/host/linux-x86/clang-r563880c/bin
  elif command -v clang >/dev/null 2>&1; then CLANG_DIR=$(dirname "$(command -v clang)")
  else echo "env.sh: no clang found; set CLANG_DIR" >&2; return 1 2>/dev/null || exit 1; fi
fi
[ -n "$CMAKE_BIN" ] || { [ -d "$_aosp/cmake/linux-x86/bin" ] && CMAKE_BIN=$_aosp/cmake/linux-x86/bin; }
[ -n "$BUILD_TOOLS_BIN" ] || { [ -d "$_aosp/build-tools/linux-x86/bin" ] && BUILD_TOOLS_BIN=$_aosp/build-tools/linux-x86/bin; }
export BITRA_ROOT HAKIOS_DIR MU_DIR CLANG_DIR CMAKE_BIN BUILD_TOOLS_BIN
