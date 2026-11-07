# Đánh giá hiệu năng QUIC (HTTP/3) so với TCP (HTTP/2)

Đồ án môn **NT531 – Đánh giá hiệu năng mạng máy tính**, Trường ĐH Công nghệ Thông tin – ĐHQG-HCM.

Repo chứa toàn bộ script dựng môi trường, chạy đo và xử lý số liệu. Mục tiêu là **ai cũng chạy lại được** thí nghiệm và ra kết quả tương tự (tính tái lập).

| Thành viên | MSSV | Phụ trách |
|---|---|---|
| Hưng (TV1) | 24520596 | Môi trường, KB3, KB4, slide |
| [Tên TV2] | [MSSV] | Công cụ đo, KB1, chứng minh bắt tay, đồ thị |
| An   (TV3) | 24520043 | KB2, mã nguồn quiche, lý thuyết, ráp báo cáo |

---

## 1. Đồ án đo gì

| Kịch bản | Câu hỏi | Bằng chứng |
|---|---|---|
| **KB1** – Mất gói & head-of-line blocking | Khi mạng mất gói, HTTP/3 có tải nhanh hơn HTTP/2 không? Bắt tay QUIC tốn mấy RTT so với TCP + TLS 1.3? | CSV thời gian tải, pcap, qlog |
| **KB2** – Hàng đợi trên máy chủ | Khi tải tăng dần, hàng đợi của TCP (backlog kernel) và QUIC (một socket UDP, xử lý ở userspace) đầy và bỏ gói khác nhau thế nào? | `nstat`, `ss`, so sánh mô hình M/M/1 |
| **KB3** – Dịch chuyển kết nối | Client đổi địa chỉ giữa lúc tải: TCP có đứt không, QUIC có tải tiếp không, gián đoạn bao lâu? | CSV, pcap (TCP RST), qlog (PATH_CHALLENGE / PATH_RESPONSE) |
| **KB4** – Tiêu thụ tài nguyên | Server tốn bao nhiêu CPU, RAM cho mỗi GB gửi đi qua HTTP/2 và HTTP/3? GSO giúp được bao nhiêu? | `pidstat`, `perf`, CPU-giây/GB |

## 2. Môi trường thử nghiệm

Ba "máy" là ba **network namespace** trên cùng một máy Ubuntu, nối bằng dây ảo (veth). Router ở giữa tạo điều kiện mạng bằng **NetEm** và đổi địa chỉ client bằng **NAT**.

```
            đường 1: 10.0.1.2 ── veth ── 10.0.1.1 ┐
 [client]                                         [router] 10.0.2.1 ── veth ── 10.0.2.2 [server]
            đường 2: 10.0.3.2 ── veth ── 10.0.3.1 ┘   │                         nginx :443
                                                     NetEm (trễ, mất gói, băng thông)   TCP = HTTP/2
                                                     NAT 10.0.2.101 / .102 (KB3)        UDP = HTTP/3
```

| Thành phần | Phiên bản / cấu hình |
|---|---|
| Hệ điều hành | Ubuntu Server 24.04 LTS (máy đo chính thức: VPS 4 vCPU riêng) |
| Server | nginx mainline (nginx.org), HTTP/2 + HTTP/3, TLS 1.3, chứng chỉ tự ký |
| Client | curl bản static có HTTP/3 (`/opt/quic/bin/curl`) – dùng cho cả H2 và H3 |
| QUIC phụ trợ | ngtcp2 `gtlsclient` / `gtlsserver` (GnuTLS) – đo 0-RTT, client chủ động đổi đường |
| Điều kiện mạng mặc định | RTT 50 ms (25 ms mỗi chiều), 20–50 Mbit |
| Ghim CPU | server lõi 2–3, client lõi 0–1 (`taskset`) |

## 3. Cài đặt (một lần)

Yêu cầu: Ubuntu 24.04, quyền sudo, có Internet, khoảng 10 GB trống.

```bash
git clone git@github.com:hwungzxje/nt531-quic.git && cd nt531-quic
chmod +x scripts/*.sh scripts/*.py
sudo ./scripts/install_server.sh     # nginx HTTP/3, tshark, perf, sysstat, conntrack, chứng chỉ, file test (~15 phút)
sudo ./scripts/install_tools.sh      # curl HTTP/3 + build ngtcp2 (~15 phút)
```

## 4. Mỗi lần khởi động máy

Namespace mất sau khi khởi động lại, nên chạy lại:

```bash
sudo ./scripts/setup_testbed.sh
sudo ./scripts/start_server.sh                    # máy 2 vCPU: SRV_CPUS=1 sudo -E ./scripts/start_server.sh
sudo ./scripts/check_env.sh                       # phải ra "==> MỐC 1 ĐẠT"
```

## 5. Chạy từng kịch bản

```bash
# KB3 – đổi địa chỉ giữa chừng (N lần, đổi ở giây thứ 2) + mốc so sánh không đổi
sudo ./scripts/kb3_nat_rebinding.sh 20 2
sudo ./scripts/kb3_nat_rebinding.sh 20 0
sudo python3 scripts/kb3_analyze.py               # -> data/kb3/kb3_gap.csv, figures/kb3_gap.png

# KB3b – client chủ động đổi đường (ngtcp2)
sudo ./scripts/kb3_active_migration.sh 10 2s

# KB4 – CPU/RAM theo số kết nối (máy 2 vCPU: thêm CLI_CPUS=0 và SRV_CPUS=1)
sudo ./scripts/kb4_resources.sh 5 20 "1 5 10 20 50"
sudo ./scripts/kb4_perf.sh h3 20 && sudo ./scripts/kb4_perf.sh h2 20
python3 scripts/kb4_plot.py                       # -> figures/kb4_*.png
# So sánh GSO: đổi "quic_gso off;" thành "quic_gso on;" trong config/nginx-quic.conf, chạy lại start_server + kb4_resources
```

KB1 và KB2: xem script của TV2, TV3 trong `scripts/` (đang bổ sung).

## 6. Danh sách script

| File | Việc |
|---|---|
| `scripts/install_server.sh` | Cài nginx HTTP/3 và công cụ đo |
| `scripts/install_tools.sh` | curl HTTP/3, ngtcp2 |
| `scripts/setup_testbed.sh` | Tạo 3 namespace, 2 đường cho client, địa chỉ NAT |
| `scripts/netem.sh` | `sudo ./scripts/netem.sh <trễ ms/chiều> <mất gói %> <Mbit>` hoặc `off` |
| `scripts/start_server.sh` | Chạy nginx trong namespace server |
| `scripts/check_env.sh` | Kiểm tra 9 điểm trước khi đo |
| `scripts/kb3_*.sh`, `kb3_analyze.py` | KB3 |
| `scripts/kb4_*.sh`, `kb4_plot.py` | KB4 |
| `config/nginx-quic.conf` | Cấu hình nginx dùng chung |

## 7. Quy ước dữ liệu

- **Lặp:** 20 lần mỗi cấu hình + 1 lần khởi động (`run 0`, bỏ khi xử lý). Báo cáo trung vị và khoảng tin cậy 95 %.
- **Thư mục:** `data/kbN/` (CSV – có trên GitHub), `figures/` (đồ thị), `logs/`. File lớn `pcap/`, `qlog/`, `keys/` **không** đưa lên GitHub mà để trên Drive: [link Drive].
- **Tên file:** `kb<số>_<h2|h3>_<điều kiện>_<yyyymmdd>.<đuôi>`.
- **Giải mã pcap:** mọi lần đo đều ghi khóa TLS vào `keys/sslkey.log`. Wireshark: *Preferences → Protocols → TLS → (Pre)-Master-Secret log filename*.

## 8. Lưu ý đã biết

- **GSO của nginx đang tắt mặc định** (`quic_gso off`): khi bật, nginx gộp nhiều gói QUIC thành một gói lớn nên Wireshark không giải mã được. KB4 bật lại để so sánh chi phí CPU.
- **Wireshark không thấy PATH_RESPONSE sau khi đổi đường** vì QUIC chuyển sang Connection ID mới (RFC 9000 §9.5). Dùng qlog phía client làm bằng chứng.
- **nginx bản nginx.org không hỗ trợ 0-RTT** → phần đo 0-RTT dùng `gtlsserver` cổng 4433.
- Số liệu đo trên máy ảo laptop chỉ để kiểm tra script; số liệu chính thức đo trên VPS.

## 9. Tài liệu tham khảo chính

RFC 9000 (QUIC), RFC 9001 (QUIC + TLS), RFC 9002 (phát hiện mất gói, điều khiển tắc nghẽn), RFC 9114 (HTTP/3).

## 10. Khai báo sử dụng AI

Một phần script và tài liệu được soạn với sự hỗ trợ của AI (Claude). Nhóm đã chạy, kiểm tra và chỉnh sửa toàn bộ; chi tiết khai báo trong Phụ lục B của báo cáo.
