import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('analysis',ROOT/'scripts/analyze_repository.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)

class EvidenceTests(unittest.TestCase):
    def test_duplicate_object_rejected(self):
        rows=[{'object':'obj1.bin','completed_ns':str(i)} for i in range(50)]
        with self.assertRaises(ValueError):analysis.object_metrics(rows)

    def test_original_evidence_and_saved_summary(self):
        with tempfile.TemporaryDirectory() as td:
            result=analysis.analyze(ROOT,Path(td))
        self.assertEqual(result['historical_files_hash_verified'],1139)
        self.assertEqual(result['csv_files'],381)
        self.assertEqual(result['kb1_loss_groups'],16)

class CheckEnvironmentTests(unittest.TestCase):
    def run_check(self,bad=False):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'ip').write_text('''#!/usr/bin/env python3
import os,sys
args=sys.argv[1:]
if args[:2]==['netns','exec']:
    if 'ping' in args or args[-1]=='true': sys.exit(0)
    v='3' if '--http3-only' in args else '2'
    if os.environ.get('FAKE_BAD')=='1':v='1.1'
    print(v+',200,1024',end='')
    sys.exit(0)
sys.exit(2)
''')
            (p/'curl').write_text('#!/bin/sh\necho "curl Features: HTTP2 HTTP3"\n')
            for f in p.iterdir():f.chmod(0o755)
            env={**os.environ,'PATH':str(p)+os.pathsep+os.environ['PATH'],'CURL':str(p/'curl'),'FAKE_BAD':str(int(bad))}
            return subprocess.run(['bash',str(ROOT/'scripts/check_env.sh')],env=env,capture_output=True,text=True)

    def test_valid_protocol_status_size_pass(self):
        result=self.run_check();self.assertEqual(result.returncode,0,result.stderr)

    def test_http_fallback_fails_check(self):
        result=self.run_check(True);self.assertNotEqual(result.returncode,0)
        self.assertIn('Expected',result.stderr)

    def test_invalid_nginx_config_does_not_start_server(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'id').write_text('#!/bin/sh\necho 0\n')
            (p/'ip').write_text('#!/bin/sh\necho "$*" >> "$CALL_LOG"\nexit 4\n')
            (p/'nginx').write_text('#!/bin/sh\nexit 0\n')
            (p/'test.conf').write_text('invalid;\n')
            for f in ['id','ip','nginx']:(p/f).chmod(0o755)
            env={**os.environ,'PATH':str(p)+os.pathsep+os.environ['PATH'],'NGINX':str(p/'nginx'),'CALL_LOG':str(p/'calls')}
            result=subprocess.run(['bash',str(ROOT/'scripts/start_server.sh'),str(p/'test.conf')],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            calls=(p/'calls').read_text().splitlines()
            self.assertEqual(len(calls),1)
            self.assertIn(' -t -c ',calls[0])

if __name__=='__main__':unittest.main()
