# Dữ liệu Bảng 4.2 — tải 50 object

## Điều kiện đo

- Client 10.0.1.2, server 10.0.2.2, qua namespace router.
- NetEm trên veth-rc và veth-rs: delay 25 ms mỗi chiều,
  giới hạn 50 Mbit/s, loss 0%, 1%, 5%, 10% mỗi chiều.
- Mỗi lượt tải song song 50 object, mỗi object 102400 byte,
  trên một kết nối. Hai giao thức dùng /opt/quic/bin/curl.
- URL: https://10.0.2.2/kb1_50obj/obj1.bin đến obj50.bin.
- Các object là bản sao của /var/www/testfiles/100kb.bin.
- H2/H3 được chạy xen kẽ. Giới hạn thời gian mỗi transfer là 120 s.
- Thu đủ 20 lượt thành công cho mỗi giao thức tại mỗi mức loss.

## File và cách tính

- loss*_h*_run*.csv: 160 CSV thô, mỗi file gồm 50 object.
- bang42_ms.csv: bảng trung vị, đơn vị ms.
- failed_attempts.csv: 8 lần H2 thất bại ở loss 10%.
- prior_failure.txt: ghi chú hồi cứu về 1 lần H2 thất bại trước đó.
- Script: scripts/kb1_50objects_measure.py, tính từ gốc repo.

completed_ns là thời điểm sửa cuối của file đầu ra trong /dev/shm
trừ thời điểm bắt đầu gọi curl, đơn vị nanosecond.
Đây là phép đo hoàn tất ghi file ở client, có ảnh hưởng của
bộ đệm ghi, lịch chạy tiến trình và độ phân giải timestamp hệ thống.

Trong từng lượt:
- Object đầu: min(completed_ns).
- Cả trang: max(completed_ns).
- Khoảng đứng dài nhất: chênh lệch lớn nhất giữa hai thời điểm
  hoàn tất liên tiếp đã sắp xếp, không gồm khoảng chờ object đầu.
- Chia cho 1000000 để đổi sang ms.

Lấy trung vị riêng của từng chỉ số qua 20 lượt thành công.
Không suy trực tiếp nguyên nhân HOL blocking từ khoảng đứng.

## Lượt thất bại và giới hạn

Có 9 lần H2 thất bại ở loss 10% với curl 92, PROTOCOL_ERROR.
Trung vị chỉ mô tả các lượt hoàn tất thành công.
Script chạy bổ sung sau lỗi để thu đủ 20 lượt thành công.
Nguyên nhân reset stream chưa được xác định.

Trong quá trình chẩn đoán tại loss 10%, mức error_log của Nginx
được đổi từ warn sang info và reload. Các lượt trước và sau
thay đổi này được giữ trong cùng bộ dữ liệu.
Lượt chẩn đoán riêng không được tính vào 160 CSV này.

AI hỗ trợ viết script và diễn giải kết quả. Dữ liệu được thu
bằng thực nghiệm trên VM của nhóm.
