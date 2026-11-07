# Hồ sơ phân tích KB2 — TV3

Nguồn: 30 lượt H2/H3 × c={10,25,50} × 5 lần và 12 lượt H3 c=50 trong ba khối ABBA. Không gộp dữ liệu VM. Các archive trong `raw/` giữ nguyên byte; SHA-256 nằm trong `data/archive_manifest.json`.

## Nội dung

- `data/kb2_runs.csv`: 42 hàng, từng lượt gắn archive, run_id và đường dẫn h2load nguồn.
- `data/baseline_summary.csv`, `abba_summary.csv`: trung vị, min, max, số mẫu; không phải dữ liệu gộp từng request.
- `data/kb2_socket_samples.csv`: mẫu `ss` ABBA; socket_order là vị trí trong snapshot, không phải connection ID.
- `results/figures/`: hình số liệu tạo lại khi chạy phân tích; không kèm sơ đồ minh họa cũ.
- `scripts/analyze.py`: mã xử lý log và vẽ các biểu đồ số liệu.
- `scripts/recompute.py`: kiểm checksum, giải nén có lọc và chạy phân tích.
- `scripts/kb2_buffer_abba.py`: runner ABBA đã có trong hồ sơ; lưu để truy vết. Không cần chạy lại trên VPS để tái tính kết quả.

## Tái tính trên máy phân tích

Cần Python 3.12+ và pandas, numpy, matplotlib. Trong thư mục đã giải nén gói này:

```bash
python -m pip install pandas numpy matplotlib
python scripts/recompute.py
```

Kết quả được tạo riêng tại `results/`. `data/` và `figures/` giữ bản dùng trong báo cáo. Tái tính không kết nối VPS và không thay cấu hình mạng.

## Định nghĩa quan trọng

- rps: request/s do h2load báo; các trường *_ms tính bằng ms, *_bytes bằng byte, *_pct bằng %.
- p50/p95/p99 và mean_ms là thống kê h2load theo lượt; không gọi mean_ms là TTFB. Trung vị của các p99 không phải p99 gộp của tất cả request.
- UDP/NetEm/listen counter: giá trị sau trừ trước ở cùng namespace/giao diện.
- server_idle_pct: trung bình các mẫu theo thời gian của hai lõi 2–3 trong mpstat, không phải CPU% riêng của Nginx. Khoảng monitor có thể bao gồm khởi động/thu dọn.
- A có rb=212992 byte/socket (208 KiB); B có rb=4194304 byte/socket (4 MiB). Hai socket phía server; không cộng rb rồi gọi đó là sức chứa một socket.
- started−done không được tự cộng vào succeeded hoặc failed.
- `little_requests` = rps × mean_ms/1000, là ước lượng số request trong toàn phạm vi đo, chưa được kiểm chứng bằng chuỗi L độc lập.
- Các lượt trong cùng khối ABBA không được coi tự động là các lần lặp độc lập; báo cáo dùng mô tả và so sánh trong khối.

## Kết luận có đủ bằng chứng

Tăng UDP receive buffer trong sáu lượt B loại bỏ ΔUdpRcvbufErrors được ghi nhận, tăng p50, giảm p99 và không tăng thông lượng. Chưa có bằng chứng accept queue TCP tràn; bộ đo dùng kết nối lâu dài và không phải thí nghiệm tốc độ tạo kết nối mới. Kết quả áp dụng cho triển khai và điều kiện đã đo.

Nguồn này được bổ sung từ hồ sơ KB2 đã cung cấp trước, không nằm trong ZIP repository gốc. Đầu vào còn thiếu được liệt kê tại [checklist](../../docs/RELEASE_CHECKLIST.md).

Bản repository này không kèm `figures/` dựng sẵn; chạy `recompute.py` để sinh hình trong `results/figures/`.
