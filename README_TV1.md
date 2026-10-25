# Bộ script TV1 – chép vào repo nt531-quic

scripts/install_server.sh     cài nginx HTTP/3 (nginx.org), tshark, perf..., chứng chỉ, file test
scripts/install_tools.sh      curl HTTP/3 (static) + build ngtcp2 gtlsclient/gtlsserver
scripts/setup_testbed.sh      tạo 3 namespace client – router – server (chạy lại sau mỗi lần khởi động máy)
scripts/netem.sh              đặt delay/loss/rate trên router
scripts/start_server.sh       chạy nginx trong namespace server (lõi 2-3)
scripts/check_env.sh          kiểm tra mốc 1
scripts/kb3_nat_rebinding.sh  KB3a: đổi địa chỉ giữa chừng, HTTP/2 vs HTTP/3
scripts/kb3_active_migration.sh KB3b: client chủ động đổi đường (ngtcp2)
scripts/kb3_analyze.py        tính thời gian gián đoạn + PATH_CHALLENGE từ pcap
scripts/kb4_resources.sh      KB4: CPU/RAM nginx theo số kết nối
scripts/kb4_perf.sh           KB4: CPU tiêu vào hàm nào
scripts/kb4_plot.py           KB4: vẽ đồ thị
config/nginx-quic.conf        cấu hình nginx HTTP/2 + HTTP/3

Thứ tự lần đầu:
  sudo ./scripts/install_server.sh && sudo ./scripts/install_tools.sh
  sudo ./scripts/setup_testbed.sh && sudo ./scripts/start_server.sh && sudo ./scripts/check_env.sh
