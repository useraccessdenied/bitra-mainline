# source this: the host environment for building HakiOS (clang, perl, shim headers)
. "$(dirname "$(readlink -f "${BASH_SOURCE:-$0}")")/env.sh" || return 1
export PERL5LIB=$HOME/.local/lib/perl5extra
export LD_LIBRARY_PATH=$HOME/.local/lib64:$HOME/.local/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export PATH=$CLANG_DIR:$HOME/.local/bin:$PATH
export CPATH=$MU_DIR/shim/include${CPATH:+:$CPATH} LIBRARY_PATH=$MU_DIR/shim/lib${LIBRARY_PATH:+:$LIBRARY_PATH}
