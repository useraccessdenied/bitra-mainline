#!/bin/bash
set -e
W=/var/home/kapil/projects/bitra/hakios/work; P=$HOME/.local
export PERL5LIB=$HOME/.local/lib/perl5extra
export PATH=/var/home/kapil/projects/bitra/roms/lineageos/a16/prebuilts/cmake/linux-x86/bin:/var/home/kapil/projects/bitra/roms/lineageos/a16/prebuilts/clang/host/linux-x86/clang-r563880c/bin:$P/bin:$PATH:/var/home/kapil/projects/bitra/roms/lineageos/a16/prebuilts/build-tools/linux-x86/bin
cd $W
if [ ! -x $P/bin/automake ]; then
  echo "=== automake"
  [ -s automake.tar.xz ] || curl -L --fail -s --retry 5 --retry-delay 5 --connect-timeout 30 -o automake.tar.xz https://ftp.gnu.org/gnu/automake/automake-1.17.tar.xz
  tar xf automake.tar.xz
  (cd automake-1.17 && ./configure --prefix=$P && make -j8 && make install) > $W/automake-build.log 2>&1
fi
automake --version | head -1
if [ ! -f $P/lib/libBlocksRuntime.a ]; then
  echo "=== BlocksRuntime"
  [ -d blocksruntime ] || git clone -q --depth 1 https://github.com/mackyle/blocksruntime.git
  (cd blocksruntime && CC=clang ./buildlib && mkdir -p $P/include $P/lib && cp BlocksRuntime/Block.h BlocksRuntime/Block_private.h $P/include/ && cp libBlocksRuntime.a $P/lib/ && ln -sf libBlocksRuntime.a $P/lib/libBlocksRuntime.so 2>/dev/null; true) > $W/blocks-build.log 2>&1
fi
ls $P/lib/libBlocksRuntime* $P/include/Block.h
if [ ! -f $P/lib/libdispatch.so ]; then
  echo "=== libdispatch"
  [ -d apple-libdispatch ] || git clone -q --depth 1 https://github.com/tpoechtrager/apple-libdispatch.git
  (cd apple-libdispatch && mkdir -p build && cd build && \
   CC=clang CXX=clang++ cmake -G Ninja -DCMAKE_CXX_FLAGS="-include atomic" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$P .. && ninja dispatch && cmake --install .) > $W/dispatch-build.log 2>&1
fi
ls $P/lib/libdispatch*
THEOS=$HOME/theos
if [ ! -x $THEOS/toolchain/linux/iphone/bin/ld ]; then
  echo "=== cctools-port build"
  (cd cctools-port/cctools && make distclean >/dev/null 2>&1 || true; \
   ./configure --prefix=$W/cctools-out --target=aarch64-apple-darwin --with-libtapi=no CC=clang CXX=clang++ CPPFLAGS="-I$P/include" LDFLAGS="-L$P/lib -L$P/lib64 -Wl,-rpath,$P/lib64 -Wl,-rpath,$P/lib" > $W/cctools-conf.log 2>&1 && make -j8 > $W/cctools-make.log 2>&1 && make install >> $W/cctools-make.log 2>&1)
  mkdir -p $THEOS/toolchain/linux/iphone/bin
  for t in ld nm otool strip lipo libtool nmedit ctf_insert codesign_allocate install_name_tool; do
    src=$(ls $W/cctools-out/bin/aarch64-apple-darwin-$t $W/cctools-out/bin/$t 2>/dev/null | head -1)
    if [ -n "$src" ]; then ln -sfn "$src" $THEOS/toolchain/linux/iphone/bin/$t; else echo "missing $t"; fi
  done
fi
if [ ! -d $THEOS/sdks/iPhoneOS16.5.sdk/usr/include ]; then
  echo "=== SDK"
  mkdir -p $THEOS/sdks
  [ -d $THEOS/sdks-git ] || git clone -q --depth 1 --filter=blob:none --sparse https://github.com/theos/sdks.git $THEOS/sdks-git
  git -C $THEOS/sdks-git sparse-checkout set iPhoneOS16.5.sdk
  ln -sfn ../sdks-git/iPhoneOS16.5.sdk $THEOS/sdks/iPhoneOS16.5.sdk
fi
ls $THEOS/toolchain/linux/iphone/bin; ls $THEOS/sdks/iPhoneOS16.5.sdk | head -3
echo DONE
