#!/usr/bin/env bash
# KB3a – Đổi địa chỉ giữa chừng (NAT rebinding) cho HTTP/2 và HTTP/3.
# Router SNAT client thành 10.0.2.101; sau SWITCH giây đổi sang 10.0.2.102 và xoá conntrack.
#   sudo ./scripts/kb3_nat_rebinding.sh [N=20] [SWITCH=2]     (SWITCH=0: không đổi – đo mốc so sánh)
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-20}; SWITCH=${2:-2}
CURL=${CURL:-/opt/quic/bin/curl}
DAY=$(date +%Y%m%d); mkdir -p data/kb3 pcap/kb3 qlog/kb3 keys
TAG=nat; [ "$SWITCH" = 0 ] && TAG=base
OUT=data/kb3/kb3_${TAG}_${DAY}.csv
[ -f "$OUT" ] || echo "proto,run,switch_at_s,exit_code,http_version,total,size" > "$OUT"
export SSLKEYLOGFILE=$PWD/keys/sslkey.log

R(){ ip netns exec router "$@"; }
# Bắt đầu mỗi lần đo: NAT client -> 10.0.2.101, xoá sạch trạng thái cũ
nat_reset(){
  R iptables -t nat -F POSTROUTING
  R iptables -F INPUT
  R iptables -t nat -A POSTROUTING -o veth-rs -s 10.0.1.0/24 -j SNAT --to-source 10.0.2.101
  R conntrack -F >/dev/null 2>&1 || true
}
# Đổi địa chỉ: thêm luật mới TRƯỚC rồi mới xoá luật cũ (không có khe hở),
# xoá toàn bộ conntrack để gói kế tiếp được NAT theo địa chỉ mới,
# và lặng lẽ bỏ gói gửi về địa chỉ cũ (giống NAT thật đã hết hạn – không trả ICMP).
nat_switch(){
  R iptables -t nat -I POSTROUTING 1 -o veth-rs -s 10.0.1.0/24 -j SNAT --to-source 10.0.2.102
  R iptables -t nat -D POSTROUTING 2
  R iptables -A INPUT -d 10.0.2.101 -j DROP
  R conntrack -F >/dev/null 2>&1 || true
  date +%s.%N > /tmp/kb3_switch_time
}
./scripts/netem.sh 25 0 20 >/dev/null          # RTT 50 ms, 20 Mbit

for run in $(seq 0 "$N"); do                    # run 0 = khởi động, bỏ khi xử lý
  for P in h2 h3; do
    FLAG=--http2; [ $P = h3 ] && FLAG=--http3-only
    nat_reset
    BASE=pcap/kb3/kb3_${P}_${TAG}_run${run}
    ip netns exec server tcpdump -q -i veth-s  -w "${BASE}_server.pcap" -U 'port 443' 2>/dev/null & TS=$!
    ip netns exec client tcpdump -q -i veth-c1 -w "${BASE}_client.pcap" -U 'port 443' 2>/dev/null & TC=$!
    sleep 0.5
    SW=""
    if [ "$SWITCH" != 0 ]; then ( sleep "$SWITCH"; nat_switch ) & SW=$!; fi
    set +e
    QD=qlog/kb3/${P}_${TAG}_run${run}; mkdir -p "$QD"            # qlog phía client (chỉ HTTP/3 có)
    RES=$(ip netns exec client env QLOGDIR="$PWD/$QD" taskset -c 0,1 "$CURL" -sk $FLAG --max-time 30 -o /dev/null \
          -w '%{http_version},%{time_total},%{size_download}' https://10.0.2.2/10mb.bin)
    RC=$?
    set -e
    [ -n "$SW" ] && { wait $SW 2>/dev/null || true; }
    sleep 0.5; kill $TS $TC 2>/dev/null || true; wait $TS $TC 2>/dev/null || true
    echo "$P,$run,$SWITCH,$RC,$RES" | tee -a "$OUT"
  done
done
R iptables -t nat -F POSTROUTING; R iptables -F INPUT
echo "Xong. CSV: $OUT  –  phân tích: sudo python3 scripts/kb3_analyze.py"
