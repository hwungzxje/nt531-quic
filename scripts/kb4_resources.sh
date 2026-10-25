#!/usr/bin/env bash
# KB4 – CPU và RAM của nginx khi phục vụ HTTP/2 vs HTTP/3 với số kết nối tăng dần.
# Cần h2load có HTTP/3 (TV2 cài). nginx lõi 2-3, h2load lõi 0-1.
#   sudo ./scripts/kb4_resources.sh [N=5] [DUR=20]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-5}; DUR=${2:-20}
H2LOAD=${H2LOAD:-h2load}
TAG=${TAG:-gso_on}                       # đặt TAG=gso_off khi chạy với quic_gso off
DAY=$(date +%Y%m%d); mkdir -p data/kb4 logs/kb4
OUT=data/kb4/kb4_${TAG}_${DAY}.csv
[ -f "$OUT" ] || echo "proto,clients,run,tag,cpu_s,cpu_pct,rss_mb,req_s,mb_s,cpu_s_per_gb" > "$OUT"
HZ=$(getconf CLK_TCK)
./scripts/netem.sh 25 0 10000 >/dev/null     # RTT 50 ms, không giới hạn băng thông

workers(){ pgrep -f 'nginx: worker' | tr '\n' ' '; }
ticks(){ local s=0; for p in $(workers); do s=$((s + $(awk '{print $14+$15}' /proc/$p/stat))); done; echo $s; }
rss_mb(){ local s=0; for p in $(workers); do s=$((s + $(awk '/VmRSS/{print $2}' /proc/$p/status))); done; echo $((s/1024)); }

for C in 1 10 50 100 200; do
  for run in $(seq 0 "$N"); do                  # run 0 = khởi động
    for P in h2 h3; do
      T=$(( C < 2 ? 1 : 2 ))
      LOG=logs/kb4/h2load_${P}_c${C}_run${run}.log
      PIDS=$(workers | tr ' ' ',' | sed 's/,$//')
      pidstat -h -u -r -p "$PIDS" 1 > logs/kb4/pidstat_${P}_c${C}_run${run}.log & PS=$!
      MAXRSS=0; ( while true; do r=$(rss_mb); echo $r; sleep 0.5; done ) > /tmp/kb4rss & RS=$!
      A=$(ticks)
      ip netns exec client taskset -c 0,1 "$H2LOAD" --alpn-list=$P -D "$DUR" --warm-up-time=2 \
          -c "$C" -t "$T" -m 1 https://10.0.2.2/1mb.bin > "$LOG" 2>&1 || true
      B=$(ticks)
      kill $PS $RS 2>/dev/null || true; wait $PS $RS 2>/dev/null || true
      MAXRSS=$(sort -n /tmp/kb4rss | tail -1)
      CPU_S=$(echo "scale=3; ($B-$A)/$HZ" | bc)
      REQ=$(grep -oP 'finished in [0-9.]+s, \K[0-9.]+(?= req/s)' "$LOG" || echo 0)
      MBS=$(grep -oP 'req/s, \K[0-9.]+(?=[KMG]?B/s)' "$LOG" || echo 0)
      UNIT=$(grep -oP 'req/s, [0-9.]+\K[KMG]?B(?=/s)' "$LOG" || echo MB)
      case $UNIT in KB) MBS=$(echo "scale=3;$MBS/1024"|bc);; GB) MBS=$(echo "scale=3;$MBS*1024"|bc);; esac
      ELAPSED=$(echo "$DUR + 2" | bc)
      PCT=$(echo "scale=1; 100*$CPU_S/$ELAPSED" | bc)
      GB=$(echo "scale=4; $MBS*$DUR/1024" | bc)
      PERGB=$( [ "$(echo "$GB > 0" | bc)" = 1 ] && echo "scale=3; $CPU_S/$GB" | bc || echo NA)
      echo "$P,$C,$run,$TAG,$CPU_S,$PCT,$MAXRSS,$REQ,$MBS,$PERGB" | tee -a "$OUT"
    done
  done
done
