"""Run the real unittest suite with per-case JSON evidence and no external mail.

python -m scripts.run_final_checks --output ../final-tests.json
Temporary databases belong to tests; an existing application data folder is never selected.
"""
import argparse
import hashlib
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RecordedResult(unittest.TextTestResult):
    def startTest(self,test):
        self.started=time.monotonic();super().startTest(test)
    def record(self,test,status,detail=None):
        self.records.append(dict(id=test.id(),description=test.shortDescription() or '',status=status,
            seconds=round(time.monotonic()-self.started,4),detail=detail))
    def addSuccess(self,test):super().addSuccess(test);self.record(test,'PASS')
    def addFailure(self,test,err):super().addFailure(test,err);self.record(test,'FAIL',self._exc_info_to_string(err,test))
    def addError(self,test,err):super().addError(test,err);self.record(test,'FAIL',self._exc_info_to_string(err,test))
    def addSkip(self,test,reason):super().addSkip(test,reason);self.record(test,'NOT TESTED',reason)
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args()
    output=Path(args.output).expanduser().resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lepka-final-') as folder:
        # Never send real email in automated acceptance. Specific tests supply explicit mocks.
        os.environ.update(LEPKA_DATA_DIR=folder,LEPKA_MAIL_API_KEY='',LEPKA_NOTIFICATION_MAIL_ENABLED='0',LEPKA_FORCE_LOCAL='0')
        sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
        from scripts.prepare_android import MODULES,VIEWS,ASSETS,NATIVE_FILES
        from scripts.prepare_server import MODULES as SERVER
        paths={*[n+'.py' for n in MODULES],*[n+'.py' for n in SERVER],*['views/'+n+'.py' for n in VIEWS],*['assets/'+n for n in ASSETS],*['native/lepka_platform/'+n for n in NATIVE_FILES],*['backend/'+p.name for p in (ROOT/'backend').glob('*.py')],'main.py'}
        hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(paths)}
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
        result=unittest.TextTestRunner(verbosity=2,resultclass=RecordedResult).run(suite)
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        data=dict(startedAtUTC=started,finishedAtUTC=datetime.now(timezone.utc).isoformat(),sourceCommit=commit,
            runtimeSHA256=hashes,runtimeUnchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in hashes.items()),
            sourceDirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
            command='python -m scripts.run_final_checks --output '+str(args.output),python=sys.version.split()[0],
            seconds=round(time.monotonic()-clock,3),total=result.testsRun,passed=sum(r['status']=='PASS' for r in result.records),
            failed=len(result.failures)+len(result.errors),notTested=len(result.skipped),cases=result.records)
        output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
