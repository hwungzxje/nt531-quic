#!/usr/bin/env bash
# KB3a – Đổi địa chỉ giữa chừng (NAT rebinding) cho HTTP/2 và HTTP/3.
# Router SNAT client thành 10.0.2.101; sau SWITCH giây đổi sang 10.0.2.102 và xoá conntrack.
# Từ phía server, client "đột nhiên" có địa chỉ mới – giống điện thoại đổi Wi-Fi sang 4G.
#   sudo ./scripts/kb3_nat_rebinding.sh [N=20] [SWITCH=2]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-20}; SWITCH=${2:-2}
CURL=${CURL:-/opt/quic/bin/curl}
DAY=$(date +%Y%m%d); mkdir -p data/kb3 pcap/kb3 keys
OUT=data/kb3/kb3_nat_${DAY}.csv
[ -f "$OUT" ] || echo "proto,run,switch_at_s,exit_code,http_version,total,size" > "$OUT"
export SSLKEYLOGFILE=$PWD/keys/sslkey.log

R(){ ip netns exec router "$@"; }
nat_to(){
  R iptables -t nat -F POSTROUTING
  R iptables -t nat -A POSTROUTING -o veth-rs -s 10.0.1.0/24 -j SNAT --to-source "$1"
  R conntrack -D -s 10.0.1.2 >/dev/null 2>&1 || true
}
./scripts/netem.sh 25 0 20 >/dev/null          # RTT 50 ms, 20 Mbit: tải 10 MB mất ~4–5 s

for run in $(seq 0 "$N"); do                    # run 0 = khởi động, bỏ khi xử lý
  for P in h2 h3; do
    FLAG=--http2; [ $P = h3 ] && FLAG=--http3-only
    nat_to 10.0.2.101
    PCAP=pcap/kb3/kb3_${P}_nat_run${run}.pcap
    ip netns exec server tcpdump -q -i veth-s -s 200 -w "$PCAP" -U 'port 443' 2>/dev/null & TD=$!
    sleep 0.5
    ( sleep "$SWITCH"; nat_to 10.0.2.102 ) & SW=$!
    set +e
    RES=$(ip netns exec client taskset -c 0,1 "$CURL" -sk $FLAG --max-time 30 -o /dev/null \
          -w '%{http_version},%{time_total},%{size_download}' https://10.0.2.2/10mb.bin)
    RC=$?
    set -e
    wait $SW 2>/dev/null || true
    sleep 0.5; kill $TD 2>/dev/null || true; wait $TD 2>/dev/null || true
    echo "$P,$run,$SWITCH,$RC,$RES" | tee -a "$OUT"
  done
done
R iptables -t nat -F POSTROUTING
echo "Xong. CSV: $OUT  –  phân tích: python3 scripts/kb3_analyze.py"
