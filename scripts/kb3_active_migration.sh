#!/usr/bin/env bash
# KB3b – Client CHỦ ĐỘNG đổi đường (active migration, RFC 9000 §9) bằng ngtcp2 gtlsclient.
# Client tự mở socket mới sau DUR rồi gửi tiếp trên đường mới -> server phải PATH_CHALLENGE.
#   sudo ./scripts/kb3_active_migration.sh [N=10] [DUR=2s]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-10}; DUR=${2:-2s}
CLI=${CLI:-/opt/quic/bin/gtlsclient}
mkdir -p pcap/kb3 qlog/kb3 data/kb3 keys
export SSLKEYLOGFILE=$PWD/keys/sslkey.log
./scripts/netem.sh 25 0 20 >/dev/null
OUT=data/kb3/kb3_active_$(date +%Y%m%d).csv
[ -f "$OUT" ] || echo "run,exit_code,total_s" > "$OUT"
for run in $(seq 1 "$N"); do
  PCAP=pcap/kb3/kb3_h3_active_run${run}.pcap
  ip netns exec server tcpdump -q -i veth-s -s 200 -w "$PCAP" -U 'udp port 443' 2>/dev/null & TD=$!
  sleep 0.5
  T0=$(date +%s.%N)
  set +e
  ip netns exec client timeout 60 "$CLI" -q --exit-on-all-streams-close --change-local-addr="$DUR" \
     --qlog-dir=qlog/kb3 --download=/tmp/kb3dl 10.0.2.2 443 https://10.0.2.2/10mb.bin >/dev/null 2>logs_kb3_active.err
  RC=$?
  set -e
  T1=$(date +%s.%N)
  sleep 0.5; kill $TD; wait $TD 2>/dev/null || true
  echo "$run,$RC,$(echo "$T1 - $T0" | bc)" | tee -a "$OUT"
done
