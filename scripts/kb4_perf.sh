#!/usr/bin/env bash
# KB4 – xem CPU của nginx tiêu vào đâu (mã hoá, gửi UDP, xử lý QUIC...).
#   sudo ./scripts/kb4_perf.sh h3 100     (proto, số kết nối)
set -euo pipefail
cd "$(dirname "$0")/.."
P=${1:-h3}; C=${2:-100}; CURL=${CURL:-/opt/quic/bin/curl}
mkdir -p logs/kb4
W=$(pgrep -f 'nginx: worker' | head -1)
FLAG=--http2; [ "$P" = h3 ] && FLAG=--http3-only
URLS=$(for i in $(seq 1 400); do printf -- '-o /dev/null https://10.0.2.2/1mb.bin '; done)
for i in $(seq 1 "$C"); do
  ip netns exec client timeout 25 taskset -c "${CLI_CPUS:-0,1}" "$CURL" -sk $FLAG $URLS >/dev/null 2>&1 &
done
sleep 5
perf record -F 499 -g -p "$W" -o logs/kb4/perf_${P}_c${C}.data -- sleep 15
wait || true
perf report -i logs/kb4/perf_${P}_c${C}.data --stdio --no-children --sort symbol --percent-limit 1.5 \
  > logs/kb4/perf_${P}_c${C}.txt 2>/dev/null
head -60 logs/kb4/perf_${P}_c${C}.txt
