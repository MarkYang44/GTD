#!/usr/bin/env bash
# Build relocatable native tools from checksummed upstream releases.
set -euo pipefail

cd "$(dirname "$0")/.."
output="$PWD/build/media"
sources="$output/sources"
mkdir -p "$sources" "$output/bin" "$output/licenses"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() {
  local name=$1 url=$2 hash=$3 actual temporary
  if [[ ! -f "$sources/$name" ]]; then
    temporary="$sources/.$name.part"
    curl --fail --location --retry 3 --silent --show-error "$url" -o "$temporary"
    mv "$temporary" "$sources/$name"
  fi
  if command -v sha256sum >/dev/null; then
    actual=$(sha256sum "$sources/$name")
  else
    actual=$(shasum -a 256 "$sources/$name")
  fi
  if [[ ${actual%% *} != "$hash" ]]; then
    echo "Invalid SHA-256 for $sources/$name" >&2
    return 1
  fi
  tar -xf "$sources/$name" -C "$work"
}

ffmpeg=ffmpeg-8.1.3
lame=lame-3.100
aria=aria2-1.37.0
zlib=zlib-1.4

case "$(uname -s)/$(uname -m)" in
  Darwin/arm64)
    jobs=${GTD_BUILD_JOBS:-$(sysctl -n hw.ncpu)}
    suffix=
    ffmpeg_tls=--enable-securetransport
    aria_tls=--with-appletls
    aria_static=no
    export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-13.5}
    tool_ldflags=
    ;;
  MINGW*/x86_64|UCRT*/x86_64)
    jobs=${GTD_BUILD_JOBS:-$(nproc)}
    suffix=.exe
    ffmpeg_tls=--enable-schannel
    aria_tls=--with-wintls
    aria_static=yes
    tool_ldflags='-static -static-libgcc -static-libstdc++'
    ;;
  *)
    echo "Build on arm64 macOS or in an MSYS2 UCRT64 shell on Windows x64." >&2
    exit 1
    ;;
esac
fetch "$ffmpeg.tar.xz" "https://ffmpeg.org/releases/$ffmpeg.tar.xz" \
  7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3
fetch "$lame.tar.gz" "https://downloads.sourceforge.net/project/lame/lame/3.100/$lame.tar.gz" \
  ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e
fetch "$aria.tar.xz" "https://github.com/aria2/aria2/releases/download/release-1.37.0/$aria.tar.xz" \
  60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b

prefix="$work/deps"
mkdir -p "$prefix/include" "$prefix/lib"
if [[ $suffix == .exe ]]; then
  fetch "$zlib.tar.xz" "https://github.com/madler/zlib/releases/download/v1.4/$zlib.tar.xz" \
    4f11c512053d7bab8d9e9b89bde3575add3e4c50a383b42ef6cb837035fc5a7c
  (
    cd "$work/$zlib"
    make -j"$jobs" -f win32/Makefile.gcc libz.a
    cp zlib.h zconf.h "$prefix/include/"
    cp libz.a "$prefix/lib/"
    cp LICENSE "$output/licenses/zlib.txt"
  )
fi

(
  cd "$work/$lame"
  ./configure --prefix="$prefix" --enable-static --disable-shared \
    --disable-frontend --disable-gtktest --disable-dependency-tracking
  make -j"$jobs" install
  cp COPYING "$output/licenses/LAME.txt"
)

(
  cd "$work/$ffmpeg"
  ./configure --disable-autodetect --disable-shared --enable-static \
    --disable-doc --disable-ffplay --disable-devices --enable-indev=lavfi \
    --enable-libmp3lame --enable-zlib \
    "$ffmpeg_tls" --extra-cflags="-I$prefix/include" \
    --extra-ldflags="-L$prefix/lib $tool_ldflags"
  make -j"$jobs" ffmpeg"$suffix" ffprobe"$suffix"
  strip ffmpeg"$suffix" ffprobe"$suffix"
  cp ffmpeg"$suffix" ffprobe"$suffix" "$output/bin/"
  cp COPYING.LGPLv2.1 "$output/licenses/FFmpeg-LGPLv2.1.txt"
  cp LICENSE.md "$output/licenses/FFmpeg.txt"
)

(
  cd "$work/$aria"
  ARIA2_STATIC="$aria_static" CPPFLAGS="-I$prefix/include" LDFLAGS="-L$prefix/lib $tool_ldflags" \
    ./configure "$aria_tls" --without-openssl --without-gnutls --without-libnettle \
    --without-libgmp --without-libgcrypt --without-sqlite3 --without-libcares \
    --without-libxml2 --without-libexpat --without-libssh2 --disable-bittorrent \
    --disable-metalink --disable-websocket --disable-nls
  make -j"$jobs" -C src aria2c"$suffix"
  strip src/aria2c"$suffix"
  if [[ $suffix == .exe ]]; then
    objdump -p src/aria2c.exe | awk '/DLL Name:/ { print $NF }'
  fi
  cp src/aria2c"$suffix" "$output/bin/"
  cp COPYING "$output/licenses/aria2.txt"
)

"$output/bin/ffmpeg$suffix" -version
"$output/bin/ffprobe$suffix" -version
"$output/bin/aria2c$suffix" --version
