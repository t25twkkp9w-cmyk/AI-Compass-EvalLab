import csv,io,json,os,sqlite3,hashlib,uuid,threading,time
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from fastapi import FastAPI,HTTPException,Header,Depends
from fastapi.responses import Response,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from dotenv import load_dotenv
from typing import Literal
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
# No remote trace claims when no credential is configured.
if not os.getenv('LANGSMITH_API_KEY'):os.environ['LANGSMITH_TRACING']='false'
from backend.engine import run_case,aggregate,FIXES,POLICIES
RUNTIME=Path(os.getenv('EVALLAB_DATA_DIR',str(ROOT/'runtime')));RUNTIME.mkdir(parents=True,exist_ok=True)
DB=RUNTIME/'evallab.sqlite3'
def connect():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;return c
with connect() as c:
 c.executescript('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, body TEXT); CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, body TEXT); CREATE TABLE IF NOT EXISTS audits(id INTEGER PRIMARY KEY, at TEXT, action TEXT, body TEXT); CREATE TABLE IF NOT EXISTS judgments(id TEXT PRIMARY KEY, body TEXT);')
 # Interrupted processes never leave a permanently running experiment.
 for row in c.execute('SELECT id,body FROM runs').fetchall():
  run=json.loads(row['body'])
  if run['status']=='running':run['status']='interrupted';c.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(run),row['id']))
def now():return datetime.now(timezone.utc).isoformat()
def audit(action,body):
 with connect() as c:c.execute('INSERT INTO audits(at,action,body) VALUES(?,?,?)',(now(),action,json.dumps(body)))
def dataset():
 cases=json.loads((ROOT/'data/cases.json').read_text())
 with connect() as c:reviews={r['id']:json.loads(r['body']) for r in c.execute('SELECT * FROM reviews')}
 for case in cases:
  if case['id'] in reviews:case.update(reviews[case['id']])
 return cases
def fingerprint(cases):return hashlib.sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest()[:16]
def save(run):
 with connect() as c:c.execute('INSERT OR REPLACE INTO runs VALUES(?,?)',(run['id'],json.dumps(run)))
def get_run(id):
 with connect() as c:r=c.execute('SELECT body FROM runs WHERE id=?',(id,)).fetchone()
 if not r:raise HTTPException(404,'Run not found')
 return json.loads(r['body'])
def write_access(authorization:str|None=Header(default=None)):
 token=os.getenv('EVALLAB_API_TOKEN','')
 if os.getenv('EVALLAB_PUBLIC_READONLY','false').lower()=='true' and not token:raise HTTPException(403,'This deployment is read only')
 if token:
  import hmac
  if not authorization or not hmac.compare_digest(authorization,'Bearer '+token):raise HTTPException(401,'Operator token required')
app=FastAPI(title='AI Compass EvalLab',version='1.0.0')
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3200','http://localhost:3200'],allow_methods=['GET','POST'],allow_headers=['Content-Type','Authorization'])
@app.get('/api/health')
def health():return {'status':'ok','app':'AI Compass EvalLab'}
@app.get('/api/status')
def status():
 return {'mode':'demo','model_available':bool(os.getenv('OPENAI_API_KEY')),'langsmith_configured':bool(os.getenv('LANGSMITH_API_KEY')),'langsmith_required':True,'trace_status':'Configured; delivery must be verified' if os.getenv('LANGSMITH_API_KEY') else 'Not connected','model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'public_readonly':os.getenv('EVALLAB_PUBLIC_READONLY','false')=='true','policies':POLICIES,'fixes':FIXES}
@app.get('/api/dataset')
def get_dataset():
 cases=dataset();return {'version':fingerprint(cases),'cases':cases,'reviewed':sum(c['review_status']=='reviewed' for c in cases),'provenance':'40 AI-authored fictional examples. Not independently validated ground truth. Replace or supplement before course submission; handout limits purely LLM-generated cases to below 20%.'}
class Expected(BaseModel):
 decision:Literal['allow','conditional','block','review','clarify']
 conditions:list[str]
 citations:list[str]
 route:Literal['none','Security','Governance']
 tools:list[str]
class Review(BaseModel):
 reviewer:str=Field(min_length=2,max_length=100)
 rationale:str=Field(min_length=10,max_length=2000)
 expected:Expected
@app.post('/api/dataset/{case_id}/review',dependencies=[Depends(write_access)])
def review(case_id:str,body:Review):
 if case_id not in [c['id'] for c in dataset()]:raise HTTPException(404,'Case not found')
 if not set(body.expected.citations)<=set(p['id'] for p in POLICIES):raise HTTPException(422,'Unknown policy citation')
 data={'expected':body.expected.model_dump(),'review_status':'reviewed','reviewer':body.reviewer,'label_rationale':body.rationale,'reviewed_at':now()}
 with connect() as c:c.execute('INSERT OR REPLACE INTO reviews VALUES(?,?)',(case_id,json.dumps(data)))
 audit('label_review',{'case_id':case_id,**data});return data
class RunRequest(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 fixes:list[Literal['data_guard','conditions','current_sources','recovery']]=[]
 mode:Literal['demo','live']='demo'
 scope:Literal['all','reviewed']='all'
lock=threading.Lock()
def worker(run):
 try:
  for case in run['dataset']:
   run['results'].append(run_case(case,run['fixes'],run['mode']));save(run)
  run['metrics']=aggregate(run['results']);run['status']='completed';run['completed_at']=now();save(run);audit('run_completed',{'run_id':run['id'],'mode':run['mode']})
 except Exception as e:run['status']='failed';run['error']=type(e).__name__;save(run)
 finally:lock.release()
@app.post('/api/runs',dependencies=[Depends(write_access)])
def start(body:RunRequest):
 if body.mode=='live' and not (os.getenv('OPENAI_API_KEY') and os.getenv('LANGSMITH_API_KEY')):raise HTTPException(409,'Live runs require both OpenAI and LangSmith credentials. No silent demo fallback.')
 cases=dataset();cases=[c for c in cases if body.scope=='all' or c['review_status']=='reviewed']
 if not cases:raise HTTPException(422,'No reviewed cases available')
 if not lock.acquire(False):raise HTTPException(409,'An experiment is already running')
 run=dict(id=str(uuid.uuid4()),name=body.name,fixes=sorted(set(body.fixes)),mode=body.mode,scope=body.scope,dataset=cases,dataset_version=fingerprint(cases),policy_version=fingerprint(POLICIES),created_at=now(),status='running',results=[],metrics={},reviewed=sum(c['review_status']=='reviewed' for c in cases),trace_delivery='unverified' if body.mode=='live' else 'local only')
 save(run);threading.Thread(target=worker,args=(run,),daemon=True).start();audit('run_started',{'run_id':run['id'],'name':run['name']});return run
@app.get('/api/runs')
def runs():
 with connect() as c:items=[json.loads(r['body']) for r in c.execute('SELECT body FROM runs ORDER BY rowid DESC')]
 return [{k:v for k,v in r.items() if k not in ['dataset','results']}|{'progress':len(r['results']),'total':len(r['dataset'])} for r in items]
@app.get('/api/runs/{id}')
def run(id:str):return get_run(id)
@app.get('/api/compare')
def compare(baseline:str,candidate:str):
 a=get_run(baseline);b=get_run(candidate)
 if a['status']!='completed' or b['status']!='completed':raise HTTPException(409,'Both runs must complete')
 if any(a[k]!=b[k] for k in ['dataset_version','policy_version','mode']):raise HTTPException(409,'Comparison requires identical dataset, policy version, and execution mode')
 deltas={k:None if a['metrics'][k]['value'] is None or b['metrics'][k]['value'] is None else round(b['metrics'][k]['value']-a['metrics'][k]['value'],3) for k in a['metrics']}
 ar={r['case_id']:r for r in a['results']};regressions=[];improved=[]
 for r in b['results']:
  old=ar[r['case_id']]
  if old['passed'] and not r['passed']:regressions.append(r['case_id'])
  if not old['passed'] and r['passed']:improved.append(r['case_id'])
 clusters=Counter(f for r in a['results'] for f in r['failures'])
 return {'baseline':a['metrics'],'candidate':b['metrics'],'deltas':deltas,'regressions':regressions,'improved':improved,'failure_clusters':clusters.most_common(),'dataset_version':a['dataset_version']}
@app.get('/api/runs/{id}/export')
def export(id:str,format:Literal['json','csv']='json'):
 r=get_run(id)
 if format=='json':return Response(json.dumps(r,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="evallab-{id}.json"'})
 s=io.StringIO();writer=csv.writer(s);writer.writerow(['case_id','family','scenario','expected','output','passed','failures','latency_ms','scores'])
 for c in r['results']:writer.writerow([c['case_id'],c['family'],c['scenario'],json.dumps(c['expected']),json.dumps(c['output']),c['passed'],','.join(c['failures']),c['latency_ms'],json.dumps(c['scores'])])
 return Response(s.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="evallab-{id}.csv"'})
@app.get('/api/audit')
def audits():
 with connect() as c:return [dict(r)|{'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM audits ORDER BY id DESC LIMIT 200')]
class Judgment(BaseModel):
 reviewer:str=Field(min_length=2,max_length=100)
 supported:bool
 rationale:str=Field(min_length=10,max_length=2000)
@app.post('/api/runs/{id}/cases/{case_id}/judgment',dependencies=[Depends(write_access)])
def judgment(id:str,case_id:str,body:Judgment):
 r=get_run(id)
 if not any(c['case_id']==case_id for c in r['results']):raise HTTPException(404,'Result not found')
 entry=body.model_dump()|{'run_id':id,'case_id':case_id,'at':now()}
 with connect() as c:c.execute('INSERT OR REPLACE INTO judgments VALUES(?,?)',(id+case_id,json.dumps(entry)))
 audit('human_judgment',entry);return entry
@app.get('/api/judgments')
def judgments():
 with connect() as c:return [json.loads(r['body']) for r in c.execute('SELECT body FROM judgments')]
# Serve the exported Next.js UI on Render and locally after build.
out=ROOT/'frontend/out'
if out.exists():app.mount('/',StaticFiles(directory=out,html=True),name='frontend')
