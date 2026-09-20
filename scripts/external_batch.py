"""Run a bounded application batch with durable logs and a reusable external queue."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from external_guard import Guard, key, linkedin
import scan_portals as sp

RUNNER=Path('/opt/job-hunter/deploy/job-autopilot')
SCRIPTS=Path(__file__).resolve().parent
APPS=SCRIPTS.parent/'applications'


def main():
    with (RUNNER/'batch.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('Another application batch is active.');return 0
        guard=Guard()
        if guard.status()['remaining']==0:
            print(json.dumps(guard.status()));return 0
        batch=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        logs=RUNNER/'logs';logs.mkdir(exist_ok=True)
        snapshot=APPS/'_scan_results_latest.json'
        config_changed = snapshot.exists() and (SCRIPTS/'portals.yml').stat().st_mtime > snapshot.stat().st_mtime
        if not snapshot.exists() or config_changed or time.time()-snapshot.stat().st_mtime>14400:
            with (logs/(batch+'-discovery.log')).open('w') as out:
                subprocess.run(['python3',str(SCRIPTS/'scan_portals.py'),'--all','--min-grade','C'],stdout=out,stderr=subprocess.STDOUT,timeout=600,check=False)
        try:data=json.loads(snapshot.read_text())
        except (OSError,ValueError):data={'jobs':[]}
        queue=[]
        config=sp.load_config()
        inc=config['filters']['include'];exc=config['filters']['exclude']
        applied=sp.load_applied_index();triaged=sp.load_triaged_index()
        for job in data.get('jobs',[]):
            if linkedin(job.get('url','')) or not job.get('submittable',True):continue
            if not sp.title_ok(job.get('title',''),inc,exc):continue
            if sp.already_applied(job,applied) or sp.canonical_job_url(job.get('url','')) in triaged:continue
            decision=guard.check(job.get('url',''),job.get('company',''),batch)
            if decision.startswith('STOP:'):continue
            queue.append(job)
        queue.sort(key=lambda j:(j.get('workplace')!='remote',-j.get('score',0)))
        (APPS/'_external_queue_current.json').write_text(json.dumps({'batch':batch,'progress':guard.status(batch),'jobs':queue},indent=2))
        env=os.environ.copy();env['JOBHUNT_BATCH_ID']=batch;env['JOBHUNT_APPLICATIONS']=str(APPS)
        env['DISPLAY']=':99'
        stdout=logs/(batch+'-applications.txt');stderr=logs/(batch+'-stderr.txt')
        prompt=(RUNNER/'prompt-vps.md').read_text()
        # Always load Habib's permanent recording instruction for this run.
        prompt+='\n'+(SCRIPTS/'INTERVIEW-QA.md').read_text()+'\n'
        prompt+='\nRuntime batch: '+batch+'\nProgress before batch: '+json.dumps(guard.status(batch))+'\n'
        code=0
        with stdout.open('w') as out,stderr.open('w') as err:
            try:
                r=subprocess.run(['claude','--chrome','--model','opus','-p',prompt],cwd=RUNNER,env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,timeout=2700)
                code=r.returncode
            except subprocess.TimeoutExpired:
                code=124;err.write('Bounded batch timeout; unresolved reservations remain protected from duplicate submission.\n')
        shutil.copy2(stdout,logs/'last-output.txt');shutil.copy2(stderr,logs/'last-stderr.txt')
        status=Guard().status(batch)
        (APPS/'_external_daily_progress.json').write_text(json.dumps(status,indent=2))
        with (logs/'history.log').open('a') as history:history.write(f'{dt.datetime.now().isoformat()} batch={batch} exit={code} confirmed={status["confirmed"]}/{status["target"]}\n')
        print(json.dumps(status))
        return code

if __name__=='__main__':raise SystemExit(main())
