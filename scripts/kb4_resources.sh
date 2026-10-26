#!/usr/bin/env bash
# KB4 – CPU và RAM của nginx khi phục vụ HTTP/2 vs HTTP/3 với số kết nối tăng dần.
# Tạo tải bằng C tiến trình curl chạy song song (cùng một client cho H2 và H3 -> so sánh công bằng);
# mỗi tiến trình giữ 1 kết nối và tải liên tục file 1 MB cho tới hết DUR giây.
#   sudo ./scripts/kb4_resources.sh [N=3] [DUR=20] [CLIENTS="1 5 10 20 50"]
#   Máy 2 vCPU: SRV_CPUS=1 CLI_CPUS=0 ; máy 4 vCPU: mặc định server 2,3 – client 0,1
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-3}; DUR=${2:-20}; CLIENTS=${3:-"1 5 10 20 50"}
CURL=${CURL:-/opt/quic/bin/curl}; CLI_CPUS=${CLI_CPUS:-0,1}
TAG=${TAG:-$(grep -q 'quic_gso on;' config/nginx-quic.conf && echo gso_on || echo gso_off)}
DAY=$(date +%Y%m%d); mkdir -p data/kb4 logs/kb4
OUT=data/kb4/kb4_${TAG}_${DAY}.csv
[ -f "$OUT" ] || echo "proto,clients,run,tag,cpu_s,cpu_pct,rss_mb,mb_s,cpu_s_per_gb,errors" > "$OUT"
HZ=$(getconf CLK_TCK)
./scripts/netem.sh 25 0 10000 >/dev/null     # RTT 50 ms, không giới hạn băng thông

workers(){ pgrep -f 'nginx: worker' | tr '\n' ' '; }
ticks(){ local s=0; for p in $(workers); do s=$((s + $(awk '{print $14+$15}' /proc/$p/stat))); done; echo $s; }
rss_mb(){ local s=0; for p in $(workers); do s=$((s + $(awk '/VmRSS/{print $2}' /proc/$p/status))); done; echo $((s/1024)); }
URLS=$(for i in $(seq 1 400); do printf -- '-o /dev/null https://10.0.2.2/1mb.bin '; done)

one_client(){   # $1=flag $2=end_epoch $3=file
  while [ "$(date +%s)" -lt "$2" ]; do
    ip netns exec client timeout $(( $2 - $(date +%s) + 1 )) taskset -c "$CLI_CPUS" "$CURL" -sk $1 \
       -w '%{size_download}\n' $URLS 2>/dev/null >> "$3" || true
  done
}

for C in $CLIENTS; do
  for run in $(seq 0 "$N"); do                  # run 0 = khởi động
    for P in h2 h3; do
      FLAG=--http2; [ $P = h3 ] && FLAG=--http3-only
      TMP=$(mktemp -d)
      PIDS=$(workers | tr ' ' ',' | sed 's/,$//')
      pidstat -h -u -r -p "$PIDS" 1 > logs/kb4/pidstat_${TAG}_${P}_c${C}_run${run}.log & PS=$!
      ( while true; do rss_mb; sleep 0.5; done ) > "$TMP/rss" & RS=$!
      A=$(ticks); T0=$(date +%s.%N); END=$(( $(date +%s) + DUR ))
      for i in $(seq 1 "$C"); do one_client "$FLAG" "$END" "$TMP/c$i" & done
      wait $(jobs -p | grep -v -e "^$PS\$" -e "^$RS\$") 2>/dev/null || true
      B=$(ticks); T1=$(date +%s.%N)
      kill $PS $RS 2>/dev/null || true; wait $PS $RS 2>/dev/null || true
      BYTES=$(cat "$TMP"/c* 2>/dev/null | awk '{s+=$1} END{print s+0}')
      ERR=$(cat "$TMP"/c* 2>/dev/null | awk '$1==0{e++} END{print e+0}')
      MAXRSS=$(sort -n "$TMP/rss" | tail -1); rm -rf "$TMP"
      EL=$(echo "$T1 - $T0" | bc -l)
      CPU_S=$(echo "scale=3; ($B-$A)/$HZ" | bc -l)
      PCT=$(echo "scale=1; 100*$CPU_S/$EL" | bc -l)
      MBS=$(echo "scale=2; $BYTES/1048576/$EL" | bc -l)
      GB=$(echo "scale=4; $BYTES/1073741824" | bc -l)
      PERGB=$( [ "$(echo "$GB > 0" | bc -l)" = 1 ] && echo "scale=2; $CPU_S/$GB" | bc -l || echo NA)
      echo "$P,$C,$run,$TAG,$CPU_S,$PCT,$MAXRSS,$MBS,$PERGB,$ERR" | tee -a "$OUT"
    done
  done
done
