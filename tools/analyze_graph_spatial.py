"""Reproduce proxy-agreement statistics from preserved raw cases."""
import gzip,json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATHS=[ROOT/'agent_notes/benchmarks/2026-11-05-v010-spatial-quality-02',ROOT/'agent_notes/benchmarks/2026-11-05-v010-spatial-speed-06']
def ranks(values):
 order=sorted(range(len(values)),key=values.__getitem__);r=[0.]*len(values);i=0
 while i<len(values):
  j=i+1
  while j<len(values) and values[order[j]]==values[order[i]]:j+=1
  for k in range(i,j):r[order[k]]=(i+j-1)/2
  i=j
 return r
errors=[];predicted=[];measured=[];disagreements=0;floor_errors=[]
for path in PATHS:
 for line in gzip.decompress((path/'episodes.jsonl.gz').read_bytes()).decode().splitlines():
  row=json.loads(line)
  for f,actual in row.get('actual',{}).items():
   prediction=row['predicted'][int(f)];p={r['occurrenceId']:r for r in prediction['rooms']}
   if prediction['daylightAccessProxy'] is not None and actual['daylightAccessProxy'] is not None:floor_errors.append(abs(prediction['daylightAccessProxy']-actual['daylightAccessProxy']))
   for r in actual['rooms']:
    x=p[r['occurrenceId']]['daylightAccessProxy'];y=r['daylightAccessProxy']
    predicted.append(x);measured.append(y);errors.append(abs(x-y));disagreements+=(x>=.35)!=(y>=.35)
a,b=ranks(predicted),ranks(measured);ma=statistics.mean(a);mb=statistics.mean(b)
correlation=sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
result=dict(inputs=[str(p.relative_to(ROOT)) for p in PATHS],roomReferences=len(errors),meanAbsoluteError=statistics.mean(errors),
 p95AbsoluteError=sorted(errors)[int(.95*len(errors))],maxAbsoluteError=max(errors),
 perFloorMeanAbsoluteError=statistics.mean(floor_errors),perFloorMaxAbsoluteError=max(floor_errors),
 spearmanRankAgreement=correlation,roomThresholdDisagreements=disagreements,
 definition='Same finite-horizon potential-window-frontage proxy, independent polygon-edge geometry. Not measured daylight/illuminance accuracy.')
(ROOT/'agent_notes/benchmarks/2026-11-05-v010-spatial-verification/calibration.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
