#!/usr/bin/env bash
mkdir -p pcap data/kb1 logs

echo "1. Khởi động gtlsserver ở cổng 4433 (bật 0-RTT)..."
sudo ip netns exec server /opt/quic/bin/gtlsserver --allow-0rtt 10.0.2.2 4433 /etc/nginx/quic/key.pem /etc/nginx/quic/cert.pem > logs/server_gtls.log 2>&1 &
SERVER_PID=$!
sleep 2

echo "2. Bắt gói tin cho 1-RTT (Lần 1)..."
sudo ip netns exec client tcpdump -i any -w pcap/kb1_handshake_1rtt.pcap -s 0 'udp port 4433' > /dev/null 2>&1 &
TCPDUMP_PID=$!
sleep 1
sudo ip netns exec client /opt/quic/bin/gtlsclient --session-file=data/kb1/sess.txt --tp-file=data/kb1/tp.txt --max-data=1048576 10.0.2.2 4433 https://10.0.2.2/1mb.bin > logs/client_1rtt.log 2>&1
sleep 1
sudo kill -9 $TCPDUMP_PID 2>/dev/null || true
sleep 1

echo "3. Bắt gói tin cho 0-RTT (Lần 2)..."
sudo ip netns exec client tcpdump -i any -w pcap/kb1_handshake_0rtt.pcap -s 0 'udp port 4433' > /dev/null 2>&1 &
TCPDUMP_PID=$!
sleep 1
sudo ip netns exec client /opt/quic/bin/gtlsclient --session-file=data/kb1/sess.txt --tp-file=data/kb1/tp.txt --max-data=1048576 10.0.2.2 4433 https://10.0.2.2/1mb.bin > logs/client_0rtt.log 2>&1
sleep 1
sudo kill -9 $TCPDUMP_PID 2>/dev/null || true

sudo kill -9 $SERVER_PID 2>/dev/null || true
echo "=== HOÀN TẤT! File pcap lưu tại pcap/ ==="
