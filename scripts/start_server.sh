#!/usr/bin/env bash
# Khởi động lại nginx trong namespace server, ghim vào lõi 2-3.
set -euo pipefail
CONF=${1:-$(dirname "$0")/../config/nginx-quic.conf}
CONF=$(readlink -f "$CONF")
ip netns exec server nginx -s quit -c "$CONF" 2>/dev/null || true
sleep 1; pkill -f "nginx: master" 2>/dev/null || true; sleep 1
ip netns exec server nginx -t -c "$CONF"
ip netns exec server taskset -c ${SRV_CPUS:-2,3} nginx -c "$CONF"
sleep 1; pgrep -a nginx
ip netns exec server ss -lntup | grep 443
