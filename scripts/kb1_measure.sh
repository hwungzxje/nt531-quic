#!/usr/bin/env bash

if [ $# -ne 1 ]; then
    echo "Cách dùng: $0 <mức_mất_gói>"
    exit 1
fi
LOSS=$1
SIZE="1mb.bin"
RUNS=21
IP="10.0.2.2"
CURL="/opt/quic/bin/curl"
DATE=$(date +%Y%m%d)
OUT_DIR="data/kb1"
mkdir -p "$OUT_DIR"

# Bật NetEm theo chuẩn của nhóm
sudo ./scripts/netem.sh 25 $LOSS 50 > /dev/null

for PROTO in "h2" "h3"; do
    CSV_FILE="${OUT_DIR}/kb1_${PROTO}_loss${LOSS}_${DATE}.csv"
    echo "loss,rtt_ms,rate_mbit,proto,run,connect,appconnect,ttfb,total,size" > "$CSV_FILE"
    
    echo "Đang đo $PROTO với loss ${LOSS}% (20 lần)..."
    for i in $(seq 0 $((RUNS-1))); do
        # Tăng max-time lên 30s và bỏ qua thông báo lỗi (2>/dev/null)
        if [ "$PROTO" = "h2" ]; then
            CMD="sudo ip netns exec client $CURL -sk --http2 --max-time 30 -o /dev/null -w \"%{time_connect},%{time_appconnect},%{time_starttransfer},%{time_total}\" https://${IP}/${SIZE}"
        else
            CMD="sudo ip netns exec client $CURL -sk --http3 --max-time 30 -o /dev/null -w \"%{time_connect},%{time_appconnect},%{time_starttransfer},%{time_total}\" https://${IP}/${SIZE}"
        fi
        
        if [ $i -eq 0 ]; then
            eval "$CMD" 2>/dev/null || true
            continue
        fi
        
        RES=$(eval "$CMD" 2>/dev/null || echo "0,0,0,0")
        # Đảm bảo không có ký tự lạ nào lọt vào file CSV
        if [[ "$RES" == *"ERR"* || -z "$RES" ]]; then
            RES="0,0,0,0"
        fi
        echo "${LOSS},50,50,${PROTO},${i},${RES},${SIZE}" >> "$CSV_FILE"
    done
done

# Tắt NetEm
sudo ./scripts/netem.sh 25 0 50 > /dev/null || true
echo "[OK] Đã đo xong loss=${LOSS}%. File lưu tại: $OUT_DIR"
