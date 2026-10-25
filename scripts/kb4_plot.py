#!/usr/bin/env python3
"""KB4 – vẽ CPU (%), RAM (MB) và CPU-giây/GB theo số kết nối. python3 scripts/kb4_plot.py data/kb4/kb4_gso_on_*.csv"""
import sys, glob, os
import pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
files = sys.argv[1:] or glob.glob('data/kb4/kb4_*.csv')
df = pd.concat(pd.read_csv(f) for f in files); df = df[df.run > 0]
for c in ['cpu_pct', 'rss_mb', 'cpu_s_per_gb', 'mb_s']: df[c] = pd.to_numeric(df[c], errors='coerce')
g = df.groupby(['tag', 'proto', 'clients']).median(numeric_only=True).reset_index()
print(g[['tag', 'proto', 'clients', 'cpu_pct', 'rss_mb', 'mb_s', 'cpu_s_per_gb']].to_string(index=False))
os.makedirs('figures', exist_ok=True)
COL = {'h2': '#E8762B', 'h3': '#1F77B4'}
for col, lab, fn in [('cpu_pct', 'CPU của nginx (%)', 'kb4_cpu.png'),
                     ('rss_mb', 'RAM của nginx (MB)', 'kb4_ram.png'),
                     ('cpu_s_per_gb', 'CPU-giây cho mỗi GB gửi đi', 'kb4_cpu_per_gb.png')]:
    plt.figure(figsize=(6, 4))
    for (tag, p), s in g.groupby(['tag', 'proto']):
        plt.plot(s.clients, s[col], marker='o', color=COL[p], ls='-' if 'on' in tag else '--',
                 label=f"{'HTTP/2' if p == 'h2' else 'HTTP/3'} ({tag})")
    plt.xscale('log'); plt.xlabel('Số kết nối đồng thời'); plt.ylabel(lab); plt.legend(); plt.grid(alpha=.3)
    plt.tight_layout(); plt.savefig('figures/' + fn, dpi=200)
