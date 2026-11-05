import csv
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
if (out / "measurement_started.json").exists():
    raise SystemExit("Thư mục này đã bắt đầu đo. Dừng để tránh ghi đè.")

def now():
    return datetime.now().astimezone().isoformat()

metadata = {
    "started": now(),
    "server": "161.248.5.245",
    "objects": 50,
    "bytes_per_object": 102400,
    "runs_per_protocol": 20,
    "warmup_per_protocol": 1,
    "method": "client output file mtime_ns minus time before curl launch",
    "network": "Internet; no configured NetEm on client path",
}
(out / "measurement_started.json").write_text(
    json.dumps(metadata, indent=2), encoding="utf-8")
shutil.copyfile(__file__, out / "measurement_script.py")
metrics = {"2": [], "3": []}

def measure(proto, label):
    stem = f"h{proto}_{label}"
    with tempfile.TemporaryDirectory(prefix="kb1_vps_", dir="/dev/shm") as tmp:
        paths = [Path(tmp) / f"obj{i}.bin" for i in range(1, 51)]
        cmd = [
            "/opt/quic/bin/curl", "-skS",
            "--http2" if proto == "2" else "--http3-only",
            "--parallel", "--parallel-max", "50",
            "--parallel-max-host", "1",
            "--connect-timeout", "10", "--max-time", "120",
            "-w", "%{url_effective},%{http_version},%{response_code},"
                  "%{size_download},%{conn_id},%{exitcode}\n",
        ]
        for path in paths:
            cmd += ["-o", str(path),
                    f"https://161.248.5.245/kb1_50obj/{path.name}"]

        stamp = now()
        start = time.time_ns()
        result = subprocess.run(cmd, capture_output=True, text=True)
        (out / f"{stem}.stdout.txt").write_text(result.stdout)
        (out / f"{stem}.stderr.txt").write_text(result.stderr)
        records = list(csv.reader(result.stdout.splitlines()))
        expected = {f"https://161.248.5.245/kb1_50obj/{p.name}"
                    for p in paths}

        valid = (
            result.returncode == 0 and len(records) == 50
            and all(len(r) == 6 for r in records)
            and {r[0] for r in records} == expected
            and all(r[1:4] == [proto, "200", "102400"]
                    and r[5] == "0" for r in records)
            and len({r[4] for r in records}) == 1
            and all(p.exists() and p.stat().st_size == 102400 for p in paths)
        )
        times = ([p.stat().st_mtime_ns - start for p in paths]
                 if valid else [])
        valid = valid and all(t >= 0 for t in times)

        if not valid:
            with (out / "failed_attempts.csv").open("a", newline="") as f:
                w = csv.writer(f)
                if f.tell() == 0:
                    w.writerow(["timestamp", "proto", "run", "curl_exit",
                                "returned_rows", "log_prefix"])
                w.writerow([stamp, proto, label, result.returncode,
                            len(records), stem])
            print(f"H{proto} {label}: THẤT BẠI, đã lưu log.", flush=True)
            return

        by_url = {r[0]: r for r in records}
        with (out / f"{stem}.csv").open("x", newline="") as f:
            w = csv.writer(f)
            w.writerow(["object", "completed_ns", "http", "status",
                        "bytes", "conn_id", "exitcode"])
            for path, elapsed in zip(paths, times):
                url = f"https://161.248.5.245/kb1_50obj/{path.name}"
                w.writerow([path.name, elapsed] + by_url[url][1:])

        times.sort()
        values = [times[0] / 1e6, times[-1] / 1e6,
                  max(b - a for a, b in zip(times, times[1:])) / 1e6]
        if label != "warmup":
            metrics[proto].append(values)
        print(f"H{proto} {label}: OK | đầu {values[0]:.3f} ms"
              f" | cả trang {values[1]:.3f} ms", flush=True)

for proto in ("2", "3"):
    measure(proto, "warmup")
    time.sleep(1)

for run in range(1, 21):
    order = ("2", "3") if run % 2 else ("3", "2")
    for proto in order:
        measure(proto, f"run{run:02d}")
        time.sleep(1)

with (out / "summary_ms.csv").open("x", newline="") as f:
    w = csv.writer(f)
    w.writerow(["proto", "attempts", "successful", "failed",
                "median_first_ms", "median_page_ms", "median_max_gap_ms"])
    for proto, values in metrics.items():
        medians = ([statistics.median(v) for v in zip(*values)]
                   if values else ["", "", ""])
        w.writerow([proto, 20, len(values), 20 - len(values)] + medians)
        print(f"H{proto}: {len(values)}/20 lượt hợp lệ", flush=True)

(out / "measurement_finished.json").write_text(
    json.dumps({"finished": now()}, indent=2), encoding="utf-8")
print("Đã lưu:", out)
