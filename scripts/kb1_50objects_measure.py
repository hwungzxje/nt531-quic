"""Ubuntu NetEm: đo và xuất Bảng 4.2. Chạy qua sudo trên VM testbed."""
import argparse
import csv
import fcntl
import io
import os
import re
import signal
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

LOSSES = (0, 1, 5, 10)
DEVS = ("veth-rc", "veth-rs")
PROTOS = (2, 3)
NAMES = [f"obj{i}.bin" for i in range(1, 51)]
COLUMNS = ["object", "completed_ns", "bytes", "http", "status", "conn", "exit"]


def router(*args):
    return subprocess.check_output(["ip", "netns", "exec", "router", "tc", *args], text=True)


def current_loss(dev):
    config = router("qdisc", "show", "dev", dev)
    line = next((s for s in config.splitlines() if s.startswith("qdisc netem 10:")), "")
    if not all(x in line for x in ("parent 1:1", "limit 1000", "delay 25ms")) or "rate 50Mbit" not in config:
        raise ValueError(f"{dev}: cấu hình khác testbed đã xác nhận:\n{config}")
    loss = re.search(r"\bloss (?:random )?([0-9.]+)%", line)
    return float(loss[1]) if loss else 0.0


def set_loss(dev, loss):
    router("qdisc", "change", "dev", dev, "parent", "1:1", "handle", "10:",
           "netem", "limit", "1000", "delay", "25ms", "loss", f"{loss:g}%")
    if current_loss(dev) != loss:
        raise ValueError(f"{dev}: không xác nhận được loss {loss}%")


def metrics(rows, proto):
    if len(rows) != 50 or {r["object"] for r in rows} != set(NAMES):
        raise ValueError("Lượt không đủ 50 object riêng biệt")
    if {(r["bytes"], r["http"], r["status"], r["exit"]) for r in rows} != {("102400", str(proto), "200", "0")}:
        raise ValueError("Sai giao thức, HTTP status, exit code hoặc kích thước file")
    if len({r["conn"] for r in rows}) != 1 or not rows[0]["conn"].isdigit():
        raise ValueError("Không xác nhận được một kết nối duy nhất")
    t = sorted(int(r["completed_ns"]) / 1e6 for r in rows)
    if t[0] <= 0:
        raise ValueError("Mốc thời gian không hợp lệ")
    return t[0], t[-1], max(b-a for a, b in zip(t, t[1:]))


def measure(proto):
    with tempfile.TemporaryDirectory(dir="/dev/shm") as folder:
        cmd = ["ip", "netns", "exec", "client", "/opt/quic/bin/curl", "-skS",
               "--http2" if proto == 2 else "--http3-only", "--parallel",
               "--parallel-max", "50", "--parallel-max-host", "1", "--max-time", "120",
               "-w", "%{url_effective},%{http_version},%{response_code},%{conn_id},%{exitcode}\n"]
        for name in NAMES:
            cmd.extend(["-o", str(Path(folder, name)), f"https://10.0.2.2/kb1_50obj/{name}"])
        before = time.time_ns()
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"curl {result.returncode}: {result.stderr}\nKết quả từng URL:\n{result.stdout}")
        rows = []
        for url, http, status, conn, code in csv.reader(io.StringIO(result.stdout)):
            name = url.rsplit("/", 1)[-1]
            stat = Path(folder, name).stat()
            rows.append(dict(zip(COLUMNS, [name, str(stat.st_mtime_ns-before),
                                            str(stat.st_size), http, status, conn, code])))
        metrics(rows, proto)
        return rows


def write_csv(path, columns, rows):
    temp = path.with_suffix(".tmp")
    with temp.open("w", newline="") as f:
        out = csv.writer(f)
        out.writerow(columns)
        out.writerows(rows)
    os.replace(temp, path)


def measure_with_log(folder, loss, proto, run_number):
    failures = folder / "failed_attempts.csv"
    for attempt in range(1, 4):
        print(f"Loss {loss}% | lượt hợp lệ {run_number}/20 | H{proto} | thử {attempt}/3", flush=True)
        try:
            return measure(proto)
        except (RuntimeError, ValueError, OSError) as error:
            with failures.open("a", newline="") as f:
                writer = csv.writer(f)
                if f.tell() == 0:
                    writer.writerow(["timestamp", "loss", "proto", "run", "error"])
                writer.writerow([time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                 loss, proto, run_number, str(error)])
            print(f"Lượt lỗi đã lưu: {error}", flush=True)
            if attempt == 3:
                raise RuntimeError("Ba lần liên tiếp thất bại. Dừng để kiểm tra server.") from error
            time.sleep(2)


def run(folder):
    initial = {dev: current_loss(dev) for dev in DEVS}
    table = []
    try:
        for loss in LOSSES:
            for dev in DEVS:
                set_loss(dev, loss)
            stats = {p: [] for p in PROTOS}
            for i in range(1, 21):
                for proto in (PROTOS if i % 2 else PROTOS[::-1]):
                    path = folder / f"loss{loss}_h{proto}_run{i:02}.csv"
                    if path.exists():
                        with path.open() as f:
                            rows = list(csv.DictReader(f))
                    else:
                        rows = measure_with_log(folder, loss, proto, i)
                        write_csv(path, COLUMNS, ([r[k] for k in COLUMNS] for r in rows))
                    stats[proto].append(metrics(rows, proto))
            h2, h3 = ([round(statistics.median(c), 3) for c in zip(*stats[p])] for p in PROTOS)
            table.append([loss, *h2[:2], *h3[:2], h2[2], h3[2]])
    finally:
        for dev in DEVS:
            set_loss(dev, initial[dev])
    write_csv(folder / "bang42_ms.csv",
              ["loss_pct", "h2_first_ms", "h2_page_ms", "h3_first_ms", "h3_page_ms",
               "h2_max_gap_ms", "h3_max_gap_ms"], table)
    print("Bảng hoàn chỉnh (ms):", folder / "bang42_ms.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Chạy bằng sudo trên VM Ubuntu.")
    args.output.mkdir(parents=True, exist_ok=True)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    with (args.output / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.output)
