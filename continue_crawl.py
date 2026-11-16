"""Continue saved crawl batches through GitHub Actions, honoring host cooldowns."""
import base64
import json
import math
import os
import subprocess
import time
from pathlib import Path


def gh_json(path):
    return json.loads(subprocess.check_output(['gh','api',path],text=True))


def resumable(stats):
    if stats.get('coverage',{}).get('queued_urls',0)<=0:return False
    status=stats.get('crawl_status',{})
    error=status.get('last_error','')
    return not error or '; crawl paused until ' in error or error=='Server cooldown still active; preserving queue'


def resume_at(stats,now):
    pause=float(stats.get('crawl_status',{}).get('pause_until') or 0)
    if not math.isfinite(pause):raise ValueError('Invalid cooldown in saved status')
    return max(now+60,pause)


def checkpoint_published(jobs):
    required={'Save resumable checkpoint','Publish immutable index for Sites'}
    return any(required <= {s['name'] for s in job.get('steps',[]) if s.get('conclusion')=='success'} for job in jobs)


def active(runs):
    return any(r.get('status')!='completed' for r in runs)


def main():
    repo=os.environ['GITHUB_REPOSITORY']
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    def running():
        return active(gh_json(f'repos/{repo}/actions/workflows/archive.yml/runs?per_page=20')['workflow_runs'])
    if running():
        print('A crawl is already running or queued; its completion will trigger the next check.')
        return
    trigger=event.get('workflow_run')
    if trigger:
        if trigger.get('conclusion')=='cancelled':
            print('Cancelled runs are not restarted.');return
        jobs=gh_json(f'repos/{repo}/actions/runs/{int(trigger["id"])}/jobs')['jobs']
        if not checkpoint_published(jobs):
            print('No verified checkpoint and published index; automatic continuation stopped.');return
    item=gh_json(f'repos/{repo}/contents/latest.json?ref=archive-index')
    stats=json.loads(base64.b64decode(item['content']))
    if not resumable(stats):
        print('No pending URLs, or an unexpected failure needs attention; no new crawl dispatched.')
        return
    deadline=resume_at(stats,time.time())
    # A listener can wait for a long Retry-After without requesting anything from Whoa.
    # Continue very long waits in another listener job, within GitHub runner time limits.
    stop_at=min(deadline,time.time()+18000)
    print(f'Pending URLs: {stats["coverage"]["queued_urls"]}; waiting until {stop_at:.0f} before continuation.',flush=True)
    while time.time()<stop_at:time.sleep(min(30,max(0,stop_at-time.time())))
    if running():
        print('Another crawl is already running or queued; no duplicate dispatched.')
        return
    workflow='continue.yml' if time.time()<deadline else 'archive.yml'
    subprocess.run(['gh','workflow','run',workflow,'--repo',repo,'--ref','main'],check=True)
    print('Dispatched '+workflow+' on main.')


if __name__=='__main__':main()
