import csv
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1]).resolve()
base = "https://161.248.4.225/kb1_50obj"
levels = (0, 1, 5, 10)
protocols = {"2": "--http2", "3": "--http3-only"}
ns = ["ip", "netns", "exec", "kb1vps"]

def configure(loss):
    settings = ["root", "netem", "delay", "25ms", "rate", "50mbit",
                "loss", "random", f"{loss}%"]
    checks = []
    for prefix, dev in ((ns, "kb1cli"), ([], "kb1gw")):
        subprocess.run(prefix + ["tc", "qdisc", "replace", "dev", dev]
                       + settings, check=True)
        checks.append(subprocess.check_output(
            prefix + ["tc", "-s", "qdisc", "show", "dev", dev], text=True))
    with (out / f"loss{loss}_netem.txt").open("a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S %z") + "\n")
        f.writelines(checks)

def measure(proto, log):
    with tempfile.TemporaryDirectory(dir="/dev/shm") as tmp:
        files = [Path(tmp) / f"obj{i}.bin" for i in range(1, 51)]
        cmd = ns + [
            "/opt/quic/bin/curl", "-skS", protocols[proto],
            "--parallel", "--parallel-max", "50", "--parallel-max-host", "1",
            "--connect-timeout", "20", "--max-time", "180",
            "-w", "%{url_effective},%{http_version},%{response_code},"
                  "%{size_download},%{conn_id},%{exitcode}\n",
        ]
        for path in files:
            cmd += ["-o", str(path), f"{base}/{path.name}"]

        start = time.time_ns()
        result = subprocess.run(cmd, capture_output=True, text=True)
        (log / "curl.stdout").write_text(result.stdout)
        (log / "curl.stderr").write_text(result.stderr)
        (log / "curl_exit.txt").write_text(f"{result.returncode}\n")

        rows = list(csv.reader(result.stdout.splitlines()))
        expected = {f"{base}/{p.name}" for p in files}
        if (result.returncode != 0 or len(rows) != 50
                or any(len(r) != 6 for r in rows)
                or {r[0] for r in rows} != expected
                or any(r[1:4] != [proto, "200", "102400"] or r[5] != "0"
                       for r in rows)
                or len({r[4] for r in rows}) != 1
                or any(not p.is_file() or p.stat().st_size != 102400
                       for p in files)):
            return None

        data = [(p.name, p.stat().st_mtime_ns - start) for p in files]
        return data if all(t >= 0 for _, t in data) else None

def metrics(times):
    times = sorted(times)
    return (times[0] / 1e6, times[-1] / 1e6,
            max(b - a for a, b in zip(times, times[1:])) / 1e6)

summary = []
for loss in levels:
    configure(loss)
    values = {"2": [], "3": []}

    for run in range(1, 21):
        order = ("2", "3") if run % 2 else ("3", "2")
        for proto in order:
            label = f"loss{loss}_h{proto}_run{run:02d}"
            path = out / f"{label}.csv"

            if path.exists():
                with path.open(newline="") as f:
                    times = [int(r["completed_ns"]) for r in csv.DictReader(f)]
                if len(times) != 50:
                    raise SystemExit(f"CSV chưa đủ 50 dòng: {path}")
            else:
                for attempt in range(1, 4):
                    log = Path(tempfile.mkdtemp(prefix=f"{label}_", dir=out))
                    print(f"{label} | thử {attempt}/3", flush=True)
                    data = measure(proto, log)
                    if data is not None:
                        temp = path.with_suffix(".tmp")
                        with temp.open("w", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow(["object", "completed_ns"])
                            writer.writerows(data)
                        temp.replace(path)
                        (log / "result.txt").write_text("valid\n")
                        break
                    (log / "result.txt").write_text("failed\n")
                    print(f"Lượt lỗi, xem {log}", flush=True)
                    time.sleep(2)
                else:
                    raise SystemExit(f"{label}: 3 lượt lỗi. Dừng và giữ dữ liệu.")
                times = [t for _, t in data]
                time.sleep(1)

            row = metrics(times)
            values[proto].append(row)
            print(f"{label}: OK | cả trang {row[1]:.3f} ms", flush=True)

    for proto, rows in values.items():
        summary.append([loss, proto, len(rows),
                        *(statistics.median(col) for col in zip(*rows))])

with (out / "summary_ms.csv").open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["loss_pct", "proto", "valid_runs", "median_first_ms",
                     "median_page_ms", "median_max_gap_ms"])
    writer.writerows(summary)

print(f"Đã lưu bảng tổng hợp: {out / 'summary_ms.csv'}", flush=True)
