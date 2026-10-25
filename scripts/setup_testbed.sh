#!/usr/bin/env bash
# Tạo testbed 3 namespace: client – router – server (chạy bằng sudo).
#   client: 10.0.1.2 (đường 1, veth-c1)  và 10.0.3.2 (đường 2, veth-c2)
#   router: 10.0.1.1 (veth-rc) / 10.0.3.1 (veth-rc2) / 10.0.2.1 (veth-rs)
#           + 10.0.2.101, 10.0.2.102 dùng làm địa chỉ NAT cho KB3
#   server: 10.0.2.2 (veth-s)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Chạy bằng sudo"; exit 1; }

for ns in client router server; do ip netns del "$ns" 2>/dev/null || true; done
for ns in client router server; do ip netns add "$ns"; ip -n "$ns" link set lo up; done

ip link add veth-c1 type veth peer name veth-rc
ip link add veth-c2 type veth peer name veth-rc2
ip link add veth-s  type veth peer name veth-rs
ip link set veth-c1 netns client;  ip link set veth-c2 netns client
ip link set veth-rc netns router;  ip link set veth-rc2 netns router; ip link set veth-rs netns router
ip link set veth-s  netns server

ip -n client addr add 10.0.1.2/24 dev veth-c1
ip -n client addr add 10.0.3.2/24 dev veth-c2
ip -n router addr add 10.0.1.1/24 dev veth-rc
ip -n router addr add 10.0.3.1/24 dev veth-rc2
ip -n router addr add 10.0.2.1/24 dev veth-rs
ip -n router addr add 10.0.2.101/24 dev veth-rs
ip -n router addr add 10.0.2.102/24 dev veth-rs
ip -n server addr add 10.0.2.2/24 dev veth-s

for d in veth-c1 veth-c2; do ip -n client link set "$d" up; done
for d in veth-rc veth-rc2 veth-rs; do ip -n router link set "$d" up; done
ip -n server link set veth-s up

ip netns exec router sysctl -qw net.ipv4.ip_forward=1
ip -n server route add default via 10.0.2.1
ip -n client route add default via 10.0.1.1
# đường 2: gói có nguồn 10.0.3.2 đi ra veth-c2
ip -n client route add default via 10.0.3.1 dev veth-c2 table 100
ip -n client rule add from 10.0.3.2 table 100
# client có 2 card: tắt rp_filter để gói trả về trên đường 2 không bị bỏ
for k in all default veth-c1 veth-c2; do ip netns exec client sysctl -qw net.ipv4.conf.$k.rp_filter=0; done

# tắt offload để tc/netem và pcap phản ánh đúng từng gói
for p in "client veth-c1" "client veth-c2" "router veth-rc" "router veth-rc2" "router veth-rs" "server veth-s"; do
  set -- $p; ip netns exec "$1" ethtool -K "$2" gro off gso off tso off >/dev/null 2>&1 || true
done

# bộ đệm UDP lớn cho QUIC (KB2, KB4)
sysctl -qw net.core.rmem_max=7500000 net.core.wmem_max=7500000

echo "== Kiểm tra =="
ip netns exec client ping -c 2 -W 1 10.0.2.2 >/dev/null && echo "OK  client(10.0.1.2) -> server"
ip netns exec client ping -c 2 -W 1 -I 10.0.3.2 10.0.2.2 >/dev/null && echo "OK  client(10.0.3.2) -> server"
