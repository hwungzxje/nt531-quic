# KB1 — tải 50 object qua Internet tới VPS

## Môi trường
- Client: VM Ubuntu, truy cập Internet qua ens33 và VMware NAT.
- Server: VPS 161.248.5.245, Nginx chạy trong namespace mạng chính.
- Nginx dùng cấu hình /etc/nginx/nginx-internet.km9ZLI.conf.
- Dùng /opt/quic/bin/curl cho cả HTTP/2 và HTTP/3.
- Không cấu hình NetEm trên đường truyền đo này.
- environment.txt lưu thời gian, phiên bản curl, tuyến mạng,
  qdisc và kết quả ping trước phép đo.
- Ping 10 gói không mất gói không có nghĩa đường truyền
  không mất gói trong toàn bộ thực nghiệm.

## Workload và cách chạy
- 50 object, mỗi object 102400 byte.
- URL: https://161.248.5.245/kb1_50obj/obj1.bin đến obj50.bin.
- Các object là bản sao của 100kb.bin trên VPS.
- Tải song song, tối đa 50 transfer, một kết nối mỗi lượt.
- HTTP/2 dùng --http2; HTTP/3 dùng --http3-only.
- Mỗi giao thức có 1 lượt warm-up, không tính vào thống kê.
- Sau warm-up chạy 20 lượt mỗi giao thức, xen kẽ thứ tự H2/H3.
- Cả 40 lượt chính thức đều hợp lệ: đủ 50 object,
  đúng phiên bản HTTP, status 200, đủ byte, một kết nối, exit 0.

## Phương pháp tính
- completed_ns là thời điểm sửa cuối của file đầu ra trong /dev/shm
  trừ thời điểm ngay trước khi gọi curl, đơn vị nanosecond.
- Đây là ước lượng hoàn thành ghi file tại client, chịu ảnh hưởng
  của bộ đệm ghi, lịch chạy tiến trình và timestamp hệ thống.
- Object đầu: min(completed_ns).
- Cả trang: max(completed_ns).
- Khoảng đứng dài nhất: khoảng cách lớn nhất giữa hai thời điểm
  hoàn thành object liên tiếp sau khi sắp xếp; không tính thời gian
  chờ object đầu tiên.
- summary_ms.csv tính trung vị của 20 lượt, đổi sang ms.
- Chỉ số khoảng đứng không trực tiếp đo HOL blocking hay thời gian
  ngừng nhận dữ liệu trên mạng.

## File minh chứng
- h2_run*.csv, h3_run*.csv: 40 CSV chính thức.
- h2_warmup.csv, h3_warmup.csv: dữ liệu warm-up.
- *.stdout.txt, *.stderr.txt: đầu ra curl của từng lượt.
- measurement_script.py: bản sao script tại thời điểm đo.
- measurement_started.json, measurement_finished.json: mốc thời gian.
- summary_ms.csv: kết quả tổng hợp.
- environment.txt: thông tin môi trường client.

## Kết quả trung vị (ms)
| Chỉ số | H2 | H3 |
|---|---:|---:|
| Object đầu | 299.925 | 219.102 |
| Cả trang | 1480.542 | 1127.130 |
| Khoảng đứng dài nhất | 178.003 | 76.271 |

Kết quả mô tả đợt đo này; không suy rộng thành kết luận
HTTP/3 luôn nhanh hơn HTTP/2 trên Internet.
