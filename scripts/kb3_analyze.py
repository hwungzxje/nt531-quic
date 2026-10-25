#!/usr/bin/env python3
"""KB3 – đọc pcap phía server, tính thời gian gián đoạn và đếm PATH_CHALLENGE/RESPONSE.
   python3 scripts/kb3_analyze.py            -> data/kb3/kb3_gap.csv + figures/kb3_gap.png
Gián đoạn = (gói dữ liệu đầu tiên server gửi tới địa chỉ MỚI) - (gói dữ liệu cuối cùng tới địa chỉ CŨ)."""
import glob, re, subprocess, os, statistics as st
import pandas as pd

OLD, NEW = '10.0.2.101', '10.0.2.102'
KEYS = 'keys/sslkey.log'

def tshark(pcap, flt, fields):
    cmd = ['tshark', '-r', pcap, '-o', f'tls.keylog_file:{KEYS}', '-Y', flt, '-T', 'fields']
    for f in fields: cmd += ['-e', f]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    return [l.split('\t') for l in out.splitlines() if l]

rows = []
for pcap in sorted(glob.glob('pcap/kb3/kb3_h[23]_nat_run*.pcap')):
    m = re.search(r'kb3_(h[23])_nat_run(\d+)', pcap); proto, run = m.group(1), int(m.group(2))
    if run == 0: continue
    big = 'frame.len > 1000'                                     # gói mang dữ liệu
    old = tshark(pcap, f'ip.src==10.0.2.2 && ip.dst=={OLD} && {big}', ['frame.time_relative'])
    new = tshark(pcap, f'ip.src==10.0.2.2 && ip.dst=={NEW} && {big}', ['frame.time_relative'])
    first_new_any = tshark(pcap, f'ip.src=={NEW}', ['frame.time_relative'])
    rst = tshark(pcap, 'tcp.flags.reset==1', ['frame.time_relative'])
    pc = tshark(pcap, 'quic.frame_type==0x1a', ['frame.time_relative']) if proto == 'h3' else []
    pr = tshark(pcap, 'quic.frame_type==0x1b', ['frame.time_relative']) if proto == 'h3' else []
    t_old = float(old[-1][0]) if old else None
    t_new = float(new[0][0]) if new else None
    rows.append(dict(proto=proto, run=run,
        t_switch=float(first_new_any[0][0]) if first_new_any else None,
        last_old=t_old, first_new_data=t_new,
        gap_ms=round((t_new - t_old) * 1000, 2) if (t_old and t_new) else None,
        recovered=bool(new), tcp_rst=len(rst), path_challenge=len(pc), path_response=len(pr)))

df = pd.DataFrame(rows)
os.makedirs('data/kb3', exist_ok=True); df.to_csv('data/kb3/kb3_gap.csv', index=False)
print(df.groupby('proto').agg(runs=('run', 'count'), recovered=('recovered', 'mean'),
      gap_median_ms=('gap_ms', 'median'), path_challenge=('path_challenge', 'mean')))

h3 = df[(df.proto == 'h3') & df.gap_ms.notna()].gap_ms
if len(h3) > 1:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    q = sorted(h3); n = len(q)
    print(f'HTTP/3 gián đoạn: trung vị {st.median(q):.1f} ms, min {q[0]:.1f}, max {q[-1]:.1f} (n={n})')
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(5, 3.5)); plt.boxplot(h3, labels=['HTTP/3 (QUIC)'], widths=.4)
    plt.ylabel('Thời gian gián đoạn (ms)'); plt.title('KB3 – gián đoạn khi đổi địa chỉ')
    plt.tight_layout(); plt.savefig('figures/kb3_gap.png', dpi=200)
