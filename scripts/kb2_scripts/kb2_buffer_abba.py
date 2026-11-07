#!/usr/bin/env python3
"""KB2 H3 buffer pilot. Run as root on the VPS, inside tmux. Python stdlib only.
Restarts ONLY the verified Nginx in kb2-server before EACH run (including B2).
Temporarily changes HOST rmem_default, as required by this kernel; run alone.
SIGINT/SIGTERM trigger restoration. SIGKILL/power loss cannot be trapped.
"""
import datetime, fcntl, hashlib, json, os, re, shutil, signal
import subprocess as sp
import sys, tarfile, tempfile, time, traceback
from pathlib import Path

BASE = Path('/opt/quic-lab')
CONF = BASE/'kb2/nginx.conf'
NGINX = str(BASE/'nginx/sbin/nginx')
H2LOAD = str(BASE/'client/bin/h2load')
PREFIX = str(BASE/'kb2')+'/'
PIDFILE = BASE/'kb2/logs/nginx.pid'
OUT = None
children = []

def run(args, check=True):
    p = sp.run(list(map(str,args)), stdout=sp.PIPE, stderr=sp.STDOUT,
               text=True, timeout=20, env={**os.environ,'LC_ALL':'C'})
    if check and p.returncode:
        raise RuntimeError(f'{args}: exit={p.returncode}\n{p.stdout}')
    return p.stdout

def ns(name, args):
    return ['ip','netns','exec',name]+list(map(str,args))

def save(path, args):
    text = run(args)
    path.write_text(text)
    return text

def note(msg):
    line = f'{datetime.datetime.now().astimezone().isoformat()} {msg}'
    print(line, flush=True)
    if OUT:
        with (OUT/'runner.log').open('a') as f: f.write(line+'\n')

def server_pids():
    pids=[]
    for token in run(['ip','netns','pids','kb2-server']).split():
        p=Path('/proc')/token
        try:
            if (p/'comm').read_text().strip()=='nginx':
                if os.path.realpath(p/'exe') != NGINX:
                    raise RuntimeError('Unexpected Nginx executable in kb2-server')
                pids.append(int(token))
        except FileNotFoundError: pass
    return pids

def stop_server():
    pids=server_pids()
    if not pids: return
    master=int(PIDFILE.read_text().strip())
    if master not in pids: raise RuntimeError('PID file does not match kb2-server')
    cmd=Path(f'/proc/{master}/cmdline').read_bytes()
    if str(CONF).encode() not in cmd or b'master process' not in cmd:
        raise RuntimeError('Refusing to stop an unverified master process')
    os.kill(master, signal.SIGTERM)
    deadline=time.monotonic()+15
    while server_pids():
        if time.monotonic()>deadline: raise RuntimeError('Nginx has not stopped; no forced kill')
        time.sleep(.2)

def start_server():
    run(ns('kb2-server',[NGINX,'-t','-p',PREFIX,'-c',CONF]))
    run(ns('kb2-server',['taskset','-c','2,3',NGINX,'-p',PREFIX,'-c',CONF]))
    time.sleep(2)
    pids=server_pids()
    if len(pids)!=3: raise RuntimeError(f'Expected master + 2 workers; got {pids}')
    for pid in pids:
        if os.sched_getaffinity(pid)!={2,3}: raise RuntimeError('Server CPU affinity mismatch')

def check_socket(text, expected, count=None):
    rb=re.findall(r'\brb(\d+)',text)
    if not rb or set(rb)!={str(expected)} or (count is not None and len(rb)!=count):
        raise RuntimeError(f'Socket buffer mismatch: expected {expected}, count={count}, got {rb}')

def stop_children():
    for p in children:
        if p.poll() is None: p.terminate()
    for p in children:
        try: p.wait(timeout=5)
        except sp.TimeoutExpired: p.kill(); p.wait()
    children.clear()

def launch(args, path):
    with path.open('w') as f:
        p=sp.Popen(list(map(str,args)),stdout=f,stderr=sp.STDOUT,
                   env={**os.environ,'LC_ALL':'C'},start_new_session=True)
    children.append(p)
    return p

def snapshot(d, label):
    (d/f'{label}-time.txt').write_text(datetime.datetime.now().astimezone().isoformat())
    for side in ['client','server']:
        save(d/f'{label}-{side}-nstat.txt',ns('kb2-'+side,['nstat','-az']))
        save(d/f'{label}-{side}-udp.txt',ns('kb2-'+side,['ss','-uanmp']))
    save(d/f'{label}-router-tc.txt',ns('kb2-router',['tc','-s','qdisc','show']))

def interrupt(signum, frame):
    raise KeyboardInterrupt(f'signal {signum}')

def main():
    global OUT
    if os.geteuid()!=0: raise RuntimeError('Run as root')
    for cmd in ['ip','ss','tc','nstat','mpstat','pidstat','taskset','sysctl']:
        if not shutil.which(cmd): raise RuntimeError(f'Missing {cmd}')
    for p in [NGINX,H2LOAD]:
        if not os.access(p,os.X_OK): raise RuntimeError(f'Missing executable {p}')
    lock=(BASE/'kb2-repeat.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for name in ['kb2-client','kb2-router','kb2-server']:
        run(ns(name,['true']))
    for pid in run(['ip','netns','pids','kb2-client']).split():
        try: comm=Path(f'/proc/{pid}/comm').read_text().strip()
        except FileNotFoundError: continue
        if comm=='h2load': raise RuntimeError('A KB2 client benchmark is already running')
    original=CONF.read_bytes()
    if original.count(b'rcvbuf=104k')!=1: raise RuntimeError('Expected exactly one rcvbuf=104k in original config')
    if len(server_pids())!=3: raise RuntimeError('Expected running KB2 master + 2 workers')
    old=run(['sysctl','-n','net.core.rmem_default']).strip()
    if int(run(['sysctl','-n','net.core.rmem_max']))<2097152:
        raise RuntimeError('rmem_max too small for condition B')
    (BASE/'logs').mkdir(exist_ok=True)
    OUT=Path(tempfile.mkdtemp(prefix='vps-kb2-buffer-abba_',dir=BASE/'logs'))
    shutil.copy2(__file__,OUT/'runner.py')
    (OUT/'nginx.original.conf').write_bytes(original)
    (OUT/'original-rmem-default.txt').write_text(old+'\n')
    (OUT/'design.json').write_text(json.dumps(dict(order=['A','B','B','A'],proto='h3',
        connections=50,threads=2,streams=10,duration=60,warmup=0,cooldown=60,
        restart_before_every_run=True,server_rb_A=212992,server_rb_B=4194304,
        client_rb=4194304,queue_sampling_seconds=1),indent=2))
    save(OUT/'nginx-version.txt',[NGINX,'-V'])
    save(OUT/'h2load-version.txt',[H2LOAD,'--version'])
    save(OUT/'uname.txt',['uname','-a'])
    testfile=BASE/'kb2/www/100kb.bin'
    (OUT/'testfile-sha256.txt').write_text(hashlib.sha256(testfile.read_bytes()).hexdigest()+'\n')
    note(f'Results: {OUT}')
    print('Emergency recovery after SIGKILL/reboot: original config and rmem value are in this directory.',flush=True)
    changed=False
    code=0
    try:
        for sig in [signal.SIGINT,signal.SIGTERM]: signal.signal(sig,interrupt)
        changed=True
        run(['sysctl','-w','net.core.rmem_default=4194304'])
        for index,condition in enumerate(['A','B','B','A'],1):
            expected=212992 if condition=='A' else 4194304
            d=OUT/f'{index:02d}_{condition}_h3_c50'; d.mkdir()
            note(f'[{index}/4] {condition}: restarting KB2 Nginx, expected rb={expected}')
            stop_server()
            CONF.write_bytes(original if condition=='A' else original.replace(b'rcvbuf=104k',b'rcvbuf=2m'))
            start_server()
            time.sleep(3)
            shutil.copy2(CONF,d/'nginx.conf')
            sock=save(d/'server-socket-check.txt',ns('kb2-server',['ss','-lunmp','sport = :443']))
            check_socket(sock,expected,2)
            snapshot(d,'before')
            cmd=ns('kb2-client',['taskset','-c','0,1',H2LOAD,'--alpn-list=h3',
                '-D','60','--warm-up-time=0','-t','2','-c','50','-m','10','https://10.0.2.2/100kb.bin'])
            (d/'command.json').write_text(json.dumps(cmd))
            bench=launch(cmd,d/'h2load.txt')
            launch(['mpstat','-P','ALL','1'],d/'system-cpu.txt')
            launch(['pidstat','-u','-r','-p',','.join(map(str,server_pids()+[bench.pid])),'1'],d/'process-cpu.txt')
            start=time.monotonic(); checked=False
            with (d/'server-queue-timeseries.txt').open('w') as q:
                while bench.poll() is None:
                    if time.monotonic()-start>100: raise RuntimeError('Benchmark exceeded 100 seconds')
                    q.write(datetime.datetime.now().astimezone().isoformat()+'\n')
                    q.write(run(ns('kb2-server',['ss','-lunmp','sport = :443'])))
                    q.flush()
                    if not checked and time.monotonic()-start>=5:
                        snapshot(d,'during')
                        check_socket((d/'during-client-udp.txt').read_text(),4194304,50)
                        checked=True
                    time.sleep(1)
            rc=bench.wait()
            stop_children()
            (d/'exit-code.txt').write_text(str(rc)+'\n')
            snapshot(d,'after')
            text=(d/'h2load.txt').read_text()
            if rc or not checked or 'Application protocol: h3' not in text or 'finished in ' not in text:
                raise RuntimeError(f'Invalid run {index}; inspect h2load.txt')
            for line in text.splitlines():
                if line.startswith(('finished in','requests:','request ')): note(line)
            note('Cooldown 60 seconds')
            time.sleep(60)
            snapshot(d,'rest60')
        note('COMPLETE 4/4')
    except BaseException:
        code=1
        (OUT/'error.txt').write_text(traceback.format_exc())
        note('STOPPED: see error.txt; restoring originals')
    finally:
        for sig in [signal.SIGINT,signal.SIGTERM]: signal.signal(sig,signal.SIG_IGN)
        stop_children()
        failures=[]
        if changed:
            try:
                stop_server()
                CONF.write_bytes(original)
                start_server()
                sock=save(OUT/'restored-server-sockets.txt',ns('kb2-server',['ss','-lunmp','sport = :443']))
                check_socket(sock,212992,2)
            except BaseException:
                failures.append(traceback.format_exc())
                # Restore the file even if restarting failed; do not kill unrelated services.
                CONF.write_bytes(original)
            try: save(OUT/'sysctl-restored.txt',['sysctl','-w','net.core.rmem_default='+old])
            except BaseException: failures.append(traceback.format_exc())
        if failures:
            code=2
            (OUT/'RESTORE-FAILED.txt').write_text('\n'.join(failures))
            note('RESTORE FAILED: inspect RESTORE-FAILED.txt; do not start another benchmark')
        else: note('RESTORE OK')
        (OUT/'script-exit-code.txt').write_text(str(code)+'\n')
        archive=str(OUT)+'.tar.gz'
        with tarfile.open(archive,'w:gz') as t: t.add(OUT,arcname=OUT.name)
        print(f'Archive: {archive}\nScript exit_code={code}',flush=True)
    return code

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc:
        print(f'PRECHECK/SETUP ERROR: {exc}',file=sys.stderr)
        sys.exit(1)
