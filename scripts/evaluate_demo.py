"""Reproduce demo baseline, isolated changes and combined results without modifying app records."""
from pathlib import Path
import sys,json,datetime,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.engine import run_case,aggregate,FIXES
ROOT=Path(__file__).resolve().parents[1]
cases=json.loads((ROOT/'data/cases.json').read_text())
version=hashlib.sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest()[:16]
experiments=[]
for name,fixes in [('Baseline',[])]+[(f,[f]) for f in FIXES]+[('Combined',FIXES)]:
 results=[run_case(c,fixes,'demo') for c in cases]
 experiments.append({'name':name,'fixes':fixes,'metrics':aggregate(results),'results':results})
report={'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'demo','dataset_version':version,'review_status':'All 40 labels pending independent human review','interpretation':'Executed synthetic rule-agent demonstration. Not existing Compass AI deployment or validated live model performance.','experiments':experiments}
(ROOT/'docs/demo-evaluation-evidence.json').write_text(json.dumps(report,indent=2))
print(json.dumps([{k:v for k,v in e.items() if k!='results'} for e in experiments],indent=2))
