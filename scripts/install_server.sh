#!/usr/bin/env bash
# Cài nginx bản mainline từ nginx.org (có HTTP/3), tạo chứng chỉ, file test. Chạy bằng sudo.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl gnupg2 ca-certificates lsb-release ubuntu-keyring bc \
  iproute2 iptables conntrack ethtool tcpdump tshark sysstat \
  python3-pandas python3-matplotlib git build-essential
apt-get install -y linux-tools-common "linux-tools-$(uname -r)" || apt-get install -y linux-tools-generic || echo "Chưa cài được perf – báo lại"
curl -fsSL https://nginx.org/keys/nginx_signing.key | gpg --dearmor -o /usr/share/keyrings/nginx-archive-keyring.gpg --yes
echo "deb [signed-by=/usr/share/keyrings/nginx-archive-keyring.gpg] http://nginx.org/packages/mainline/ubuntu $(lsb_release -cs) nginx" \
  > /etc/apt/sources.list.d/nginx.list
printf 'Package: *\nPin: origin nginx.org\nPin-Priority: 900\n' > /etc/apt/preferences.d/99nginx
apt-get update && apt-get install -y nginx
nginx -V 2>&1 | grep -q with-http_v3_module && echo "OK  nginx có HTTP/3" || { echo "LỖI: nginx không có http_v3"; exit 1; }
systemctl disable --now nginx || true      # không chạy ở namespace gốc

mkdir -p /etc/nginx/quic /var/www/testfiles /var/log/nginx
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 60 \
  -subj "/CN=quic.test" -addext "subjectAltName=IP:10.0.2.2,DNS:quic.test" \
  -keyout /etc/nginx/quic/key.pem -out /etc/nginx/quic/cert.pem 2>/dev/null
cd /var/www/testfiles
for f in "1kb 1K 1" "100kb 100K 1" "1mb 1M 1" "10mb 1M 10" "100mb 1M 100"; do
  set -- $f; [ -f $1.bin ] || dd if=/dev/urandom of=$1.bin bs=$2 count=$3 status=none
done
ls -la /var/www/testfiles
