from pathlib import Path
import re,json,hashlib,statistics,datetime,csv
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import argparse
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description='Tái tính KB2 từ log đã giải nén')
parser.add_argument('--logs',type=Path,default=ROOT/'logs')
parser.add_argument('--out',type=Path,default=ROOT/'results')
parser.add_argument('--archives',type=Path,default=ROOT/'raw')
a=parser.parse_args();LOGS=a.logs;OUT=a.out;ARCHIVES=a.archives
OUT.mkdir(parents=True,exist_ok=True)
DATA=OUT/'data';DATA.mkdir(exist_ok=True)
FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
def ms(s):
 m=re.fullmatch(r'([\d.]+)(us|ms|s)',s);return float(m[1])*{'us':.001,'ms':1,'s':1000}[m[2]]
def counters(p):return {a:int(b) for a,b in re.findall(r'^(\w+)\s+(\d+)',p.read_text(),re.M)}
def delta(p,q,key):
 a,b=counters(p),counters(q)
 assert key in a and key in b,(p,key)
 return b[key]-a[key]
def cpu(p):
 rows=[]
 for line in p.read_text().splitlines():
  a=line.split()
  if len(a)==12 and re.match(r'^\d\d:',a[0]) and a[1] in ['all','0','1','2','3']:
   rows.append([a[1]]+list(map(float,a[2:])))
 def avg(cpus,idx):return statistics.mean(r[idx] for r in rows if r[0] in cpus)
 return {'server_idle_pct':avg(['2','3'],10),'client_idle_pct':avg(['0','1'],10),'steal_all_pct':avg(['all'],7)}
rows=[];qrows=[]
for base in sorted(LOGS.iterdir()):
 baseline='repeat5' in base.name
 for d in sorted(x for x in base.iterdir() if x.is_dir()):
  text=(d/'h2load.txt').read_text()
  a=re.search(r'finished in ([\d.]+)s, ([\d.]+) req/s',text)
  r={'dataset':'baseline' if baseline else 'ABBA','archive':base.name+'.tar.gz','run_id':d.name,'proto':re.search(r'Application protocol: (\S+)',text)[1],
     'connections':int(re.search(r'_c(\d+)',d.name)[1]),'run':int(re.search(r'_r(\d+)',d.name)[1]) if baseline else int(d.name[:2]),'condition':'A' if baseline else d.name.split('_')[1],
     'duration_s':float(a[1]),'rps':float(a[2]),'source_h2load':str(d.relative_to(LOGS)/'h2load.txt')}
  a=re.search(r'requests: (\d+) total, (\d+) started, (\d+) done, (\d+) succeeded, (\d+) failed, (\d+) errored, (\d+) timeout',text)
  r.update(dict(zip(['total','started','done','succeeded','failed','errored','timeout'],map(int,a.groups()))))
  a=re.search(r'^request\s+:\s+(.*)',text,re.M)[1].split()
  r.update(dict(zip(['min_ms','max_ms','p50_ms','p95_ms','p99_ms','mean_ms','sd_ms'],map(ms,a[:7]))))
  r['exit_code']=int((d/'exit-code.txt').read_text().strip());r['unfinished']=r['started']-r['done']
  r['little_requests']=r['rps']*r['mean_ms']/1000
  for side in ['client','server']:
   pref='kb2-'+side if baseline else side
   for key,label in [('UdpRcvbufErrors','udp_rcvbuf_errors'),('TcpExtListenOverflows','listen_overflows'),('TcpExtListenDrops','listen_drops')]:
    r[side+'_'+label]=delta(d/f'before-{pref}-nstat.txt',d/f'after-{pref}-nstat.txt',key)
  def tc_drops(phase):
   paths=[d/f'{phase}-kb2-rc-tc.txt',d/f'{phase}-kb2-rs-tc.txt'] if baseline else [d/f'{phase}-router-tc.txt']
   return sum(int(v) for p in paths for v in re.findall(r'\(dropped (\d+)',p.read_text()))
  r['netem_drops']=tc_drops('after')-tc_drops('before')
  r.update(cpu(d/'system-cpu.txt'))
  udp=(d/('during-kb2-server-udp.txt' if baseline else 'server-socket-check.txt')).read_text()
  r['server_rb_bytes']=';'.join(map(str,sorted(set(map(int,re.findall(r'\brb(\d+)',udp))))))
  if not baseline:
   t0=None;t=None;ix=0
   for line in (d/'server-queue-timeseries.txt').read_text().splitlines():
    if re.match(r'^2026-',line):
     t=datetime.datetime.fromisoformat(line);t0=t0 or t;ix=0
    m=re.search(r'skmem:\(r(\d+),rb(\d+).*?,d(\d+)\)',line)
    if m:
     ix+=1;qrows.append({'archive':base.name+'.tar.gz','run_id':d.name,'condition':r['condition'],'t_s':(t-t0).total_seconds(),'socket_order':ix,'r_bytes':int(m[1]),'rb_bytes':int(m[2]),'d_cumulative':int(m[3])})
  rows.append(r)
df=pd.DataFrame(rows);df.to_csv(DATA/'kb2_runs.csv',index=False)
qdf=pd.DataFrame(qrows);qdf.to_csv(DATA/'kb2_socket_samples.csv',index=False)
metrics=['rps','p50_ms','p95_ms','p99_ms','mean_ms','server_udp_rcvbuf_errors','server_idle_pct','client_idle_pct','steal_all_pct']
for name,group in [('baseline',['proto','connections']),('ABBA',['condition'])]:
 sub=df[df.dataset==name]
 summ=sub.groupby(group)[metrics].agg(['count','median','min','max'])
 summ.columns=['_'.join(c) for c in summ.columns];summ.to_csv(DATA/f'{name.lower()}_summary.csv')
checks={'runs':len(df),'baseline_runs':int((df.dataset=='baseline').sum()),'abba_runs':int((df.dataset=='ABBA').sum()),'exit_zero':bool((df.exit_code==0).all()),'reported_request_errors_zero':bool((df[['failed','errored','timeout']]==0).all().all()),'client_buffer_drops_zero':bool((df.client_udp_rcvbuf_errors==0).all()),'netem_drops_zero':bool((df.netem_drops==0).all()),'listen_overflows_zero':bool((df.server_listen_overflows==0).all()),'listen_drops_zero':bool((df.server_listen_drops==0).all()),'all_incomplete_equal_c_m':bool((df.unfinished==df.connections*10).all())}
(DATA/'validation.json').write_text(json.dumps(checks,indent=2))
manifest=[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in ARCHIVES.glob('*.tar.gz')]
(DATA/'archive_manifest.json').write_text(json.dumps(manifest,indent=2))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':220})
colors={'h2':'#d97a21','h3':'#2376b7','A':'#8b5d3b','B':'#217b81'}
def save(fig,name):fig.tight_layout();fig.savefig(FIG/(name+'.png'),bbox_inches='tight');fig.savefig(FIG/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
b=df[df.dataset=='baseline'];ab=df[df.dataset=='ABBA']
fig,axes=plt.subplots(1,2,figsize=(10,3.7))
for proto in ['h2','h3']:
 sub=b[b.proto==proto];g=sub.groupby('connections')
 for ax,metric in zip(axes,['rps','p99_ms']):
  for c,ss in g:ax.scatter(np.full(len(ss),c)+np.linspace(-.8,.8,len(ss)),ss[metric],color=colors[proto],alpha=.5,s=20)
  ax.plot([10,25,50],g[metric].median(),marker='o',color=colors[proto],label='HTTP/'+proto[1])
for ax in axes:ax.set_xlabel('Số kết nối c (m = 10)');ax.set_xticks([10,25,50]);ax.grid(alpha=.2);ax.legend()
axes[0].set_ylabel('Thông lượng (request/s)');axes[1].set_ylabel('p99 thời gian request (ms)')
save(fig,'kb2_baseline_throughput_p99')
fig,axes=plt.subplots(1,2,figsize=(10,3.6))
for proto in ['h2','h3']:
 sub=b[b.proto==proto];g=sub.groupby('connections')
 axes[0].plot([10,25,50],g.p50_ms.median(),'-o',color=colors[proto],label='HTTP/'+proto[1])
 axes[1].plot([10,25,50],g.server_udp_rcvbuf_errors.median(),'-o',color=colors[proto],label='HTTP/'+proto[1])
for ax in axes:ax.set_xlabel('Số kết nối c (m = 10)');ax.set_xticks([10,25,50]);ax.grid(alpha=.2);ax.legend()
axes[0].set_ylabel('p50 thời gian request (ms)');axes[1].set_ylabel('ΔUdpRcvbufErrors phía server (gói)')
save(fig,'kb2_baseline_p50_drops')
fig,axes=plt.subplots(1,3,figsize=(10,3.5))
for ax,metric,title in zip(axes,['rps','p50_ms','p99_ms'],['Thông lượng (request/s)','p50 (ms)','p99 (ms)']):
 for ix,cond in enumerate(['A','B']):
  v=ab[ab.condition==cond][metric].to_numpy();ax.scatter(ix+np.linspace(-.1,.1,len(v)),v,color=colors[cond]);ax.hlines(np.median(v),ix-.2,ix+.2,color='black',linewidth=2)
 ax.set_xticks([0,1],['A: 208 KiB','B: 4 MiB']);ax.set_title(title);ax.grid(axis='y',alpha=.2)
save(fig,'kb2_abba_performance')
fig,axes=plt.subplots(1,2,figsize=(10,3.5))
for ix,cond in enumerate(['A','B']):
 sub=ab[ab.condition==cond];axes[0].scatter(ix+np.linspace(-.12,.12,len(sub)),sub.server_udp_rcvbuf_errors,color=colors[cond]);axes[0].hlines(sub.server_udp_rcvbuf_errors.median(),ix-.2,ix+.2,color='black')
 # Equal weight per run, median of socket-memory samples per run.
 v=qdf[qdf.condition==cond].groupby(['archive','run_id']).r_bytes.median()/1024
 axes[1].scatter(ix+np.linspace(-.12,.12,len(v)),v,color=colors[cond]);axes[1].hlines(v.median(),ix-.2,ix+.2,color='black')
for ax in axes:ax.set_xticks([0,1],['A: 208 KiB','B: 4 MiB']);ax.grid(axis='y',alpha=.2)
axes[0].set_ylabel('ΔUdpRcvbufErrors phía server (gói)');axes[1].set_ylabel('Trung vị skmem r mỗi lượt (KiB/socket)')
save(fig,'kb2_abba_drops_memory')
fig,axes=plt.subplots(2,1,figsize=(9,5),sharex=True)
sel=qdf[qdf.archive.str.contains('opiweyx2')]
for ax,run in zip(axes,['01_A_h3_c50','02_B_h3_c50']):
 ss=sel[sel.run_id==run]
 for ix,g in ss.groupby('socket_order'):ax.plot(g.t_s,g.r_bytes/1024,label=f'Socket {ix}',linewidth=1)
 ax.axhline(ss.rb_bytes.iloc[0]/1024,color='black',ls='--',label='Giới hạn rb');ax.set_ylabel('skmem r (KiB)');ax.set_title(run);ax.legend(ncol=3,fontsize=8);ax.grid(alpha=.2)
axes[-1].set_xlabel('Thời gian từ mẫu socket đầu tiên (s)')
save(fig,'kb2_socket_timeseries')
print(json.dumps(checks));print(df.groupby(['dataset','proto','connections','condition']).rps.median().to_string())
