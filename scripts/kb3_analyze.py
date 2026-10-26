#!/usr/bin/env python3
"""KB3 – phân tích pcap.  sudo python3 scripts/kb3_analyze.py
Gián đoạn (gap_ms) = khoảng lặng dài nhất giữa 2 gói DỮ LIỆU client nhận được, tính sau thời điểm đổi địa chỉ.
PATH_CHALLENGE/RESPONSE đếm ở pcap phía server (cần keys/sslkey.log để giải mã)."""
import glob, re, subprocess, os
import pandas as pd

KEYS = 'keys/sslkey.log'
def tshark(pcap, flt, fields, dec=False):
    cmd = ['tshark', '-r', pcap, '-Y', flt, '-T', 'fields']
    if dec: cmd += ['-o', f'tls.keylog_file:{KEYS}']
    for f in fields: cmd += ['-e', f]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    return [l.split('\t') for l in out.splitlines() if l]

rows = []
for cli in sorted(glob.glob('pcap/kb3/kb3_h[23]_*_run*_client.pcap')):
    m = re.search(r'kb3_(h[23])_(nat|base)_run(\d+)_client', cli)
    proto, tag, run = m.group(1), m.group(2), int(m.group(3))
    if run == 0: continue
    srv = cli.replace('_client.pcap', '_server.pcap')
    # gói dữ liệu client nhận (server -> client, > 1000 byte)
    t = [float(x[0]) for x in tshark(cli, 'ip.src==10.0.2.2 && frame.len > 1000', ['frame.time_relative'])]
    # thời điểm đổi địa chỉ = gói đầu tiên server thấy từ 10.0.2.102
    sw = tshark(srv, 'ip.src==10.0.2.102', ['frame.time_relative'])
    t_sw_srv = float(sw[0][0]) if sw else None
    gaps = [(t[i+1] - t[i], t[i]) for i in range(len(t) - 1)]
    gap_ms, at = (max(gaps) if gaps else (0, 0))
    pc = tshark(srv, 'quic.frame_type == 0x1a', ['frame.time_relative'], dec=True) if proto == 'h3' else []
    pr = tshark(srv, 'quic.frame_type == 0x1b', ['frame.time_relative'], dec=True) if proto == 'h3' else []
    rst = tshark(srv, 'tcp.flags.reset == 1', ['frame.time_relative']) if proto == 'h2' else []
    data_new = tshark(srv, 'ip.dst==10.0.2.102 && frame.len > 1000', ['frame.time_relative'])
    # qlog phía client: đếm frame kiểm tra đường (không cần giải mã)
    qtxt = ''.join(open(f, errors='ignore').read() for f in glob.glob(f'qlog/kb3/{proto}_{tag}_run{run}/*.sqlog'))
    q_pc, q_pr = qtxt.count('"path_challenge"'), qtxt.count('"path_response"')
    rows.append(dict(qlog_path_challenge=q_pc, qlog_path_response=q_pr,proto=proto, tag=tag, run=run,
                     data_pkts=len(t), last_data_s=round(t[-1], 3) if t else None,
                     max_gap_ms=round(gap_ms * 1000, 1), gap_starts_s=round(at, 3),
                     switched=bool(sw), data_on_new_addr=len(data_new) > 0,
                     path_challenge=len(pc), path_response=len(pr), tcp_rst=len(rst)))

df = pd.DataFrame(rows)
os.makedirs('data/kb3', exist_ok=True); df.to_csv('data/kb3/kb3_gap.csv', index=False)
pd.set_option('display.width', 200)
print(df.to_string(index=False))
print()
print(df.groupby(['tag', 'proto']).agg(runs=('run', 'count'), recovered=('data_on_new_addr', 'mean'),
      gap_median_ms=('max_gap_ms', 'median'), path_challenge=('path_challenge', 'mean'),
      qlog_pc=('qlog_path_challenge', 'mean'), qlog_pr=('qlog_path_response', 'mean')))
n = 0
try: n = sum(1 for _ in open(KEYS))
except OSError: pass
print(f'\nkeys/sslkey.log: {n} dòng' + ('  (RỖNG – tshark không giải mã được QUIC!)' if n == 0 else ''))

h3 = df[(df.proto == 'h3') & (df.tag == 'nat')].max_gap_ms
if len(h3) > 1:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    os.makedirs('figures', exist_ok=True)
    plt.figure(figsize=(5, 3.5)); plt.boxplot(h3, widths=.4); plt.xticks([1], ['HTTP/3 (QUIC)'])
    plt.ylabel('Gián đoạn dài nhất (ms)'); plt.title('KB3 – gián đoạn khi đổi địa chỉ')
    plt.tight_layout(); plt.savefig('figures/kb3_gap.png', dpi=200)
