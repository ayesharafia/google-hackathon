#!/usr/bin/env python3
"""PhysiCore v3 deterministic task ledger and proof collector. Stdlib, offline.

Evidence is a checkable record of files, hashes, executed commands and Git changes,
not proof of physical correctness. Run only inside a Git repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OPS=ROOT/'.physicore/ops'; QUEUE=OPS/'TASKS.json'; WORKLOG=OPS/'WORKLOG.md'; EVIDENCE=ROOT/'.physicore/evidence'
KINDS={'audit','product','implementation','validation','regression','documentation','research','other'}
STATES={'candidate','ready','in_progress','blocked','done'}
ZONES={'green','yellow','red'}
IGNORE_PREFIX=('.git/','.physicore/','.agents/','node_modules/','.venv/','dist/','build/')

def utc():return dt.datetime.now(dt.UTC).isoformat(timespec='seconds')
def sha(b):return hashlib.sha256(b).hexdigest()
def run_git(*args):
    p=subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,text=True,timeout=12,check=False)
    if p.returncode:raise ValueError(f'git {args[0]} failed: {p.stderr.strip()}')
    return p.stdout.strip()
def git_rev():return run_git('rev-parse','HEAD')
def git_status():return sorted(run_git('status','--porcelain','--untracked-files=all').splitlines())
def read_queue():return json.loads(QUEUE.read_text(encoding='utf-8'))
def atomic_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.v3-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def safe_repo_file(path, require=True):
    p=Path(path)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Must supply safe repository-relative file path')
    f=ROOT/p
    if not f.resolve().is_relative_to(ROOT.resolve()):raise ValueError('File escapes repository')
    if require and (not f.is_file() or f.is_symlink()):raise ValueError(f'File not found or symlink: {p}')
    return f

def validate(q):
    err=[]
    if not isinstance(q,dict) or q.get('schema_version')!=2 or not isinstance(q.get('tasks'),list):return ['Expected schema_version=2 and tasks array']
    ids=set();dep={}
    for t in q['tasks']:
        if not isinstance(t,dict):err.append('task not object');continue
        i=t.get('id')
        if not isinstance(i,str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,49}',i) or i in ids:err.append('invalid or duplicate task ID');continue
        ids.add(i)
        if not isinstance(t.get('title'),str) or not isinstance(t.get('done_when'),str) or len(t['done_when'].strip())<15:err.append(f'{i}: needs title and substantive acceptance')
        if t.get('kind') not in KINDS or t.get('status') not in STATES or t.get('zone') not in ZONES:err.append(f'{i}: invalid kind/status/zone')
        if not isinstance(t.get('priority'),int) or isinstance(t.get('priority'),bool) or not 1<=t['priority']<=5:err.append(f'{i}: invalid priority')
        d=t.get('depends_on');dep[i]=d if isinstance(d,list) else []
        if not isinstance(d,list) or not all(isinstance(x,str) for x in d):err.append(f'{i}: dependencies must be IDs')
        if t.get('status')=='done' and not t.get('evidence'):err.append(f'{i}: done missing evidence')
        if t.get('zone')!='green' and t.get('status') in {'in_progress','ready'}:err.append(f'{i}: higher-risk task may not be ready/in progress')
    for i,ds in dep.items():
        if any(x not in ids for x in ds):err.append(f'{i}: dependency missing')
    seen=set();stack=set()
    def dfs(i):
        if i in stack:err.append(f'{i}: dependency cycle');return
        if i in seen:return
        stack.add(i)
        for d in dep.get(i,[]):
            if d in ids:dfs(d)
        stack.discard(i);seen.add(i)
    for i in ids:dfs(i)
    return err

def eligible(q):
    done={t['id'] for t in q['tasks'] if t['status']=='done'}
    return [t for t in q['tasks'] if t['status']=='ready' and t['zone']=='green' and all(d in done for d in t['depends_on'])]
def next_task(q):
    running=[t for t in q['tasks'] if t['status']=='in_progress']
    if running:return min(running,key=lambda t:t['id'])
    ready=eligible(q)
    return min(ready,key=lambda t:(t['kind']!='regression',-t['priority'],t['id'])) if ready else None

def task(q,i):
    t=next((t for t in q['tasks'] if t['id']==i),None)
    if not t:raise ValueError('Task not found: '+i)
    return t

def source_ok(path):
    try:
        f=safe_repo_file(path)
        return bool(f.stat().st_size>90 and 'TODO: WRITE SPEC' not in f.read_text(errors='replace'))
    except (ValueError,OSError):return False

def refresh(q):
    done={t['id'] for t in q['tasks'] if t['status']=='done'}; promoted=[]
    for t in q['tasks']:
        if (t['status']=='candidate' and t['zone']=='green' and t.get('scoped') is True
          and t.get('source_refs') and all(d in done for d in t['depends_on'])
          and all(source_ok(s) for s in t['source_refs'])):
            t['status']='ready';promoted.append(t['id'])
    return promoted

def inventory():
    tracked=run_git('ls-files','--cached','--others','--exclude-standard').splitlines()
    files=[]
    for name in sorted(set(tracked)):
        if name.startswith(IGNORE_PREFIX):continue
        try:
            p=safe_repo_file(name)
            if p.stat().st_size>5_000_000:continue
            if not p.is_file():continue
            files.append({'path':name,'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size})
        except (OSError,ValueError):pass
    return files

def changed_since(t):
    before=set(t.get('started_dirty',[]))
    now=set(git_status())
    current=[]
    for line in now-before:
        if len(line)>3:
            name=line[3:]
            if not name.startswith(IGNORE_PREFIX):current.append(name)
    if t.get('started_head') and t['started_head']!=git_rev():
        diff=run_git('diff','--name-only',t['started_head'],'HEAD').splitlines()
        current += [n for n in diff if not n.startswith(IGNORE_PREFIX)]
    return sorted(set(current))

def append_log(s):
    WORKLOG.parent.mkdir(parents=True,exist_ok=True)
    with WORKLOG.open('a',encoding='utf-8') as f:f.write('\n'+s+'\n')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    for key in ['doctor','next','refresh','status']:sub.add_parser(key)
    s=sub.add_parser('start');s.add_argument('id')
    s=sub.add_parser('audit');s.add_argument('id')
    s=sub.add_parser('scope');s.add_argument('id');s.add_argument('--title',required=True);s.add_argument('--acceptance',required=True);s.add_argument('--source',required=True)
    s=sub.add_parser('add');s.add_argument('id');s.add_argument('--title',required=True);s.add_argument('--acceptance',required=True);s.add_argument('--source',required=True);s.add_argument('--kind',choices=sorted(KINDS),default='implementation');s.add_argument('--priority',type=int,default=3);s.add_argument('--depends-on',action='append',default=[])
    s=sub.add_parser('check');s.add_argument('id');s.add_argument('--timeout',type=int,default=90);s.add_argument('cmd',nargs=argparse.REMAINDER)
    s=sub.add_parser('proof');s.add_argument('id');s.add_argument('--summary',required=True);s.add_argument('--test',action='append',default=[],help='Relative result file created by check command')
    s=sub.add_parser('complete');s.add_argument('id');s.add_argument('--evidence',required=True);s.add_argument('--notes',required=True)
    s=sub.add_parser('block');s.add_argument('id');s.add_argument('--reason',required=True)
    s=sub.add_parser('reopen');s.add_argument('id');s.add_argument('--source',required=True)
    args=p.parse_args(argv)
    try:
        q=read_queue();errs=validate(q)
        if errs:raise ValueError('; '.join(errs))
        if args.command=='doctor':
            print(f'OK: {len(q["tasks"])} tasks, {len(eligible(q))} ready; repo={run_git("rev-parse","--show-toplevel")}');return 0
        if args.command=='status':
            for t in q['tasks']:print(f'{t["id"]:<14} {t["status"]:<12} P{t["priority"]} {t["title"]}')
            return 0
        if args.command=='next':
            t=next_task(q)
            if t:print(f'{"RESUME" if t["status"]=="in_progress" else "NEXT"} {t["id"]}: {t["title"]}\nAcceptance: {t["done_when"]}')
            else:print('NO ELIGIBLE TASK: scope the highest-value candidate after audit, or add a justified safe task. Never invent a task to appear busy.')
            return 0
        if args.command=='refresh':
            changed=refresh(q);atomic_json(QUEUE,q);print('PROMOTED',changed or 'none');return 0
        if args.command in ('add','scope'):
            if not source_ok(args.source):raise ValueError('Source spec must exist with non-placeholder content (>90 bytes)')
            if args.command=='add':
                if any(x['id']==args.id for x in q['tasks']):raise ValueError('Duplicate task ID')
                if not 1<=args.priority<=5:raise ValueError('Priority must be 1..5')
                t={'id':args.id,'title':args.title,'done_when':args.acceptance,'kind':args.kind,'priority':args.priority,'status':'candidate','zone':'green','depends_on':args.depends_on,'source_refs':[args.source],'evidence':[],'scoped':True,'notes':'Evidence-backed task proposed by agent'};q['tasks'].append(t)
            else:
                t=task(q,args.id)
                if t['status'] not in ('candidate','blocked'):raise ValueError('Scope only candidate/blocked tasks')
                t.update(title=args.title,done_when=args.acceptance,source_refs=[args.source],scoped=True,status='candidate')
            errs=validate(q)
            if errs:raise ValueError('; '.join(errs))
            promoted=refresh(q);atomic_json(QUEUE,q)
            print('SCOPED',args.id,'READY' if args.id in promoted else 'WAITING ON DEPENDENCIES');return 0
        t=task(q,args.id)
        if args.command=='start':
            if t['status']=='in_progress':print('RESUME',t['id']);return 0
            if any(x['status']=='in_progress' for x in q['tasks']):raise ValueError('Another task in progress')
            if t not in eligible(q):raise ValueError('Task is not ready/green or dependencies incomplete')
            t.update(status='in_progress',started_at=utc(),started_head=git_rev(),started_dirty=git_status())
            atomic_json(QUEUE,q);print('STARTED',args.id);return 0
        if args.command=='reopen':
            if t['status']!='blocked':raise ValueError('Only blocked tasks can be reopened')
            if not source_ok(args.source):raise ValueError('Source evidence not available')
            t.update(status='candidate',scoped=True,source_refs=[args.source]);refresh(q);atomic_json(QUEUE,q);print('REOPENED',args.id,t['status']);return 0
        if args.command=='block':
            if t['status']!='in_progress':raise ValueError('Only active task can be blocked')
            t.update(status='blocked',blocked_at=utc(),notes=args.reason)
            atomic_json(QUEUE,q);append_log(f'## {utc()} BLOCKED {args.id}\n{args.reason}')
            print('BLOCKED',args.id);return 0
        if t['status']!='in_progress':raise ValueError('Start task before evidence and completion')
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        if args.command=='audit':
            if t['kind']!='audit':raise ValueError('Audit command only for audit tasks')
            files=inventory()
            if not files:raise ValueError('No application files found, cannot prove audit of real repository')
            data={'schema_version':1,'kind':'audit','id':args.id,'started_at':t['started_at'],'captured_at':utc(),'repo':str(ROOT),'head':git_rev(),'observed_files':files[:300], 'total_files':len(files),'note':'Inventory evidence only. Agent still must document domain/product conclusions before closing.'}
            dest=EVIDENCE/(args.id+'-audit.json');atomic_json(dest,data)
            print(dest.relative_to(ROOT));return 0
        if args.command=='check':
            cmd=args.cmd
            if cmd and cmd[0]=='--':cmd=cmd[1:]
            if not cmd:raise ValueError('No command given after --')
            if not 1<=args.timeout<=600:raise ValueError('Timeout 1..600 seconds')
            if any(x in cmd for x in ['|',';','&&','>','<']):raise ValueError('No shell pipelines or metacharacters')
            if cmd[0] not in {'python','python3','pytest','npm','npx','node','cargo','go','dotnet','make','cmake','ctest','ruff'}:
                raise ValueError('Command not on local verification allowlist; execute it manually and document evidence')
            try:
                result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=args.timeout,check=False)
                stdout=(result.stdout+'\n'+result.stderr)[-100000:]; rc=result.returncode
            except subprocess.TimeoutExpired:
                stdout='TIMEOUT: command exceeded the declared test time budget';rc=124
            record={'schema_version':1,'id':args.id,'kind':'test','argv':cmd,'returncode':rc,'captured_at':utc(),'started_at':t['started_at'],'repo':str(ROOT),'head':git_rev(),'output':stdout}
            dest=EVIDENCE/(args.id+'-test-'+dt.datetime.now(dt.UTC).strftime('%Y%m%d%H%M%S%f')+'.json');atomic_json(dest,record)
            print('TEST', 'PASS' if rc==0 else 'FAIL',dest.relative_to(ROOT));return 0 if rc==0 else 1
        if args.command=='proof':
            if not args.summary.strip():raise ValueError('Nonempty summary required')
            changes=changed_since(t)
            if not changes and t['kind']!='audit':raise ValueError('No new non-kit changes detectable since task start')
            tests=[]
            for path in args.test:
                f=safe_repo_file(path)
                obj=json.loads(f.read_text())
                if obj.get('id')!=args.id or obj.get('kind')!='test' or obj.get('started_at')!=t['started_at'] or obj.get('repo')!=str(ROOT):raise ValueError('Test record not from this task/repository')
                tests.append({'file':str(f.relative_to(ROOT)),'exit_code':obj['returncode'],'argv':obj['argv']})
            if t['kind'] in {'implementation','validation','regression'} and not any(x['exit_code']==0 for x in tests):
                raise ValueError('Cannot complete code or scientific task without a successful local verification command')
            inv=inventory() if t['kind']=='audit' else []
            if t['kind']=='audit' and not inv:raise ValueError('No non-kit files to audit')
            proof={'schema_version':1,'kind':'completion','id':args.id,'repo':str(ROOT),'started_at':t['started_at'],'captured_at':utc(),'baseline_head':t['started_head'],'current_head':git_rev(),'changes':changes,'tests':tests,'audit_files':inv[:300], 'summary':args.summary}
            dest=EVIDENCE/(args.id+'-completion.json');atomic_json(dest,proof)
            print(dest.relative_to(ROOT));return 0
        if args.command=='complete':
            f=safe_repo_file(args.evidence)
            obj=json.loads(f.read_text())
            if obj.get('kind')!='completion' or obj.get('id')!=args.id or obj.get('repo')!=str(ROOT) or obj.get('started_at')!=t['started_at']:
                raise ValueError('Completion proof does not match this in-progress task')
            if t['kind']=='audit':
                for source in obj.get('audit_files',[]):
                    path=safe_repo_file(source['path'])
                    if sha(path.read_bytes())!=source['sha256']:raise ValueError('Audit evidence stale or modified')
                if not obj.get('audit_files'):raise ValueError('No real source files audited')
                state=(OPS/'STATE.md').read_text(encoding='utf-8')
                if 'Last verified run: NONE' in state or 'Demonstrated capabilities: NONE CONFIRMED BY THIS KIT' in state:
                    raise ValueError('Audit narrative in STATE.md still contains initial placeholders')
                if not any(x['path'] in state for x in obj['audit_files']):
                    raise ValueError('Audit STATE.md must cite at least one inspected real application path')
            else:
                if not obj.get('changes'):raise ValueError('No changed application files attested')
                if not set(obj['changes']).issubset(set(changed_since(t))):raise ValueError('Changes no longer present or not attributable to this run')
                if t['kind'] in ('implementation','validation','regression') and not any(x.get('exit_code')==0 for x in obj.get('tests',[])):
                    raise ValueError('Missing passing verification record')
            t.update(status='done',finished_at=utc(),notes=args.notes,evidence=[str(f.relative_to(ROOT))])
            promoted=refresh(q);atomic_json(QUEUE,q)
            append_log(f'## {utc()} DONE {args.id}\n- Evidence: {f.relative_to(ROOT)}\n- Notes: {args.notes}\n- Next ready: {", ".join(promoted) or "no new task promoted"}')
            print('DONE',args.id,'PROMOTED',promoted);return 0
        raise ValueError('Unknown command')
    except (OSError,ValueError,json.JSONDecodeError,subprocess.TimeoutExpired) as e:
        print('ERROR:',str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
