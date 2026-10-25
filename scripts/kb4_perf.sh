#!/usr/bin/env bash
# KB4 – xem CPU của nginx tiêu vào đâu (mã hoá, gửi UDP, xử lý QUIC...).
#   sudo ./scripts/kb4_perf.sh h3 100     (proto, số kết nối)
set -euo pipefail
cd "$(dirname "$0")/.."
P=${1:-h3}; C=${2:-100}; H2LOAD=${H2LOAD:-h2load}
mkdir -p logs/kb4
W=$(pgrep -f 'nginx: worker' | head -1)
ip netns exec client taskset -c 0,1 "$H2LOAD" --alpn-list=$P -D 25 -c "$C" -t 2 -m 1 https://10.0.2.2/1mb.bin >/dev/null 2>&1 &
sleep 5
perf record -F 499 -g -p "$W" -o logs/kb4/perf_${P}_c${C}.data -- sleep 15
wait || true
perf report -i logs/kb4/perf_${P}_c${C}.data --stdio --no-children --sort symbol --percent-limit 1.5 \
  > logs/kb4/perf_${P}_c${C}.txt 2>/dev/null
head -60 logs/kb4/perf_${P}_c${C}.txt
