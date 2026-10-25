#!/usr/bin/env bash
# curl có HTTP/3 (bản static) + build ngtcp2 example client/server (GnuTLS). Chạy bằng sudo.
set -euo pipefail
PREFIX=/opt/quic; mkdir -p $PREFIX/bin /opt/src
ARCH=$(uname -m)
# 1) curl HTTP/3: bản build tĩnh của dự án stunnel/static-curl (có ngtcp2 + nghttp3)
if ! $PREFIX/bin/curl -V 2>/dev/null | grep -q HTTP3; then
  URL=$(curl -fsSL https://api.github.com/repos/stunnel/static-curl/releases/latest \
        | grep -o "https://[^\"]*curl-linux-${ARCH}-glibc[^\"]*\.tar\.xz" | head -1)
  [ -n "$URL" ] || URL=$(curl -fsSL https://api.github.com/repos/stunnel/static-curl/releases/latest \
        | grep -o "https://[^\"]*curl-linux-${ARCH}[^\"]*\.tar\.xz" | head -1)
  curl -fsSL "$URL" | tar -xJ -C $PREFIX/bin
fi
$PREFIX/bin/curl -V | head -3

# 2) ngtcp2 + nghttp3 (cho KB3 phần client chủ động đổi địa chỉ, và đo 0-RTT)
apt-get install -y build-essential autoconf automake libtool pkg-config git libev-dev libgnutls28-dev
cd /opt/src
[ -d nghttp3 ] || git clone --depth 1 -b v1.8.0 https://github.com/ngtcp2/nghttp3
cd nghttp3 && git submodule update --init --depth 1 && autoreconf -i && \
  ./configure --prefix=$PREFIX --enable-lib-only && make -j"$(nproc)" && make install && cd ..
[ -d ngtcp2 ] || git clone --depth 1 -b v1.11.0 https://github.com/ngtcp2/ngtcp2
cd ngtcp2 && git submodule update --init --depth 1 && autoreconf -i && \
  ./configure --prefix=$PREFIX PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig --with-gnutls --with-libnghttp3 --with-libev && \
  make -j"$(nproc)" && make install
cp examples/gtlsclient examples/gtlsserver $PREFIX/bin/
echo "$PREFIX/lib" > /etc/ld.so.conf.d/quic.conf && ldconfig
ls $PREFIX/bin
