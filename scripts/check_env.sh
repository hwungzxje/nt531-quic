#!/usr/bin/env bash
# Mốc 1: kiểm tra testbed + nginx trả cả HTTP/2 lẫn HTTP/3. Dùng: sudo ./scripts/check_env.sh
CURL=${CURL:-/opt/quic/bin/curl}
ok(){ echo "OK   $*"; }; bad(){ echo "LỖI $*"; FAIL=1; }
FAIL=0
for ns in client router server; do ip netns list | grep -qw $ns && ok "namespace $ns" || bad "thiếu namespace $ns"; done
ip netns exec client ping -c1 -W1 10.0.2.2 >/dev/null && ok "ping đường 1" || bad "ping đường 1"
ip netns exec client ping -c1 -W1 -I 10.0.3.2 10.0.2.2 >/dev/null && ok "ping đường 2" || bad "ping đường 2"
$CURL -V | grep -q HTTP3 && ok "curl có HTTP3 ($CURL)" || bad "curl không có HTTP3"
V2=$(ip netns exec client $CURL -sk --http2 -o /dev/null -w '%{http_version}' https://10.0.2.2/1kb.bin)
[ "$V2" = 2 ] && ok "HTTP/2 trả về" || bad "HTTP/2 (được: $V2)"
V3=$(ip netns exec client $CURL -sk --http3-only -o /dev/null -w '%{http_version}' https://10.0.2.2/1kb.bin)
[ "$V3" = 3 ] && ok "HTTP/3 trả về" || bad "HTTP/3 (được: $V3)"
ip netns exec client $CURL -sk --http3-only --interface 10.0.3.2 -o /dev/null -w '%{http_version}' https://10.0.2.2/1kb.bin | grep -q 3 \
  && ok "HTTP/3 qua đường 2" || bad "HTTP/3 qua đường 2"
[ $FAIL = 0 ] && echo "==> MỐC 1 ĐẠT" || echo "==> còn lỗi"
