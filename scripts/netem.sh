#!/usr/bin/env bash
# Đặt điều kiện mạng trên router (cả 2 chiều, mọi đường).
#   sudo ./scripts/netem.sh <delay_ms_mỗi_chiều> <loss_%> <rate_mbit>   ví dụ: 25 0 50
#   sudo ./scripts/netem.sh off
set -euo pipefail
DEVS="veth-rc veth-rc2 veth-rs"
if [ "${1:-}" = off ]; then
  for d in $DEVS; do ip netns exec router tc qdisc del dev $d root 2>/dev/null || true; done; echo "netem off"; exit 0
fi
D=${1:-25}; L=${2:-0}; R=${3:-50}
for d in $DEVS; do
  ip netns exec router tc qdisc replace dev $d root netem delay ${D}ms loss ${L}% rate ${R}mbit limit 1000
done
echo "netem: delay ${D}ms/chiều (RTT $((2*D))ms), loss ${L}%, rate ${R}Mbit"
