"""Publish an immutable, public Pagefind dataset and a tiny latest pointer.

No Site credentials are needed: GitHub's repository-scoped Actions token writes
only this repository. The Site keeps an imported local fallback snapshot.
"""
import json, os, pathlib, shutil, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parent

def git(*args,cwd=ROOT,check=True):
    return subprocess.run(['git',*args],cwd=cwd,check=check,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

with tempfile.TemporaryDirectory(prefix='whoa-index-') as tmp:
    target=pathlib.Path(tmp)/'tree'
    exists=git('fetch','--no-tags','origin','refs/heads/archive-index',check=False).returncode==0
    base='FETCH_HEAD' if exists else 'HEAD'
    git('worktree','add','--detach',str(target),base)
    try:
        if not exists:git('switch','--orphan','generated-archive-index',cwd=target)
        git('config','user.name','github-actions[bot]',cwd=target)
        git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com',cwd=target)
        shutil.rmtree(target/'pagefind',ignore_errors=True)
        shutil.copytree(ROOT/'dist/pagefind',target/'pagefind')
        shutil.copy2(ROOT/'dist/stats.json',target/'stats.json')
        git('add','pagefind','stats.json',cwd=target)
        if git('diff','--cached','--quiet',cwd=target,check=False).returncode:
            git('commit','-m','Update actual Whoa archive index',cwd=target)
        data_sha=git('rev-parse','HEAD',cwd=target).stdout.strip()
        stats=json.loads((target/'stats.json').read_text())
        latest={**stats,'data_commit':data_sha,'pagefind_version':'1.4.0'}
        (target/'latest.json').write_text(json.dumps(latest,ensure_ascii=False),encoding='utf-8')
        git('add','latest.json',cwd=target)
        if git('diff','--cached','--quiet',cwd=target,check=False).returncode:
            git('commit','-m','Point Sites to the immutable archive dataset',cwd=target)
        git('push','origin','HEAD:refs/heads/archive-index',cwd=target)
        (ROOT/'dist/latest.json').write_text(json.dumps(latest,ensure_ascii=False),encoding='utf-8')
        print('Published data commit:',data_sha)
    finally:
        git('worktree','remove','--force',str(target),check=False)
