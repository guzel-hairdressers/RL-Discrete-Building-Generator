"""Isolated correctness probes against exact v0.9.0 function source.

Not a throughput/convergence benchmark. No server or production state changes.
"""
from __future__ import annotations
import ast, hashlib, json, math, subprocess, types
from pathlib import Path

REF='version/v0.9.0-alpha'
def source(path):return subprocess.check_output(['git','show',f'{REF}:{path}'],text=True)
s=source('src/server.py');g=source('src/geometry.py')

def extract(text,name):
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    return ast.unparse(node)

tree=ast.parse(s)
actual=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='SPATIAL_PADDING' for t in n.targets))
namespace=dict(math=math,SPATIAL_PADDING=actual)
geo=types.SimpleNamespace()
namespace['G']=geo
used={}
for src,name in ((g,'bounds_of'),(g,'ray_intersect_segments'),(s,'_safe_ratio'),(s,'_bounds_intersect'),
                 (s,'_narrow_facade_chasm_metrics'),(s,'_validate_edge_alignment')):
    code=extract(src,name);used[name]=hashlib.sha256(code.encode()).hexdigest()
    exec('from __future__ import annotations\n'+code,namespace)
    if name in ('bounds_of','ray_intersect_segments'):setattr(geo,name,namespace[name])

def seg(a,b):return dict(a=dict(x=a[0],y=a[1]),b=dict(x=b[0],y=b[1]),length=math.dist(a,b))
long=[seg((12,0),(0,0)),seg((0,3),(12,3))]
split=[]
for i in range(24):
    x=i*.5
    split.extend((seg((x+.5,0),(x,0)),seg((x,3),(x+.5,3))))
metric=namespace['_narrow_facade_chasm_metrics']
original=metric(None,long,24.)[0];fragmented=metric(None,split,24.)[0]
assert abs(original-9.6)<1e-9 and fragmented==0

poly=lambda x0,y0,x1,y1:[dict(x=x0,y=y0),dict(x=x1,y=y0),dict(x=x1,y=y1),dict(x=x0,y=y1)]
candidate=poly(0,0,4,4);existing=poly(5,0,9,4)
env=types.SimpleNamespace(placement_by_id={'other':dict(poly=existing)},placement_bounds={'other':geo.bounds_of(existing)},
    _nearby_placement_ids=lambda _:['other'],_bounds_intersect=namespace['_bounds_intersect'])
accepted=namespace['_validate_edge_alignment'](env,candidate)
assert accepted is True

august_sources={path:subprocess.check_output(['git','show',f'main:{path}'],text=True)
                for path in ('src/server.py','src/geometry.py')}
august_checks={}
for name,expected in used.items():
    path='src/geometry.py' if name in ('bounds_of','ray_intersect_segments') else 'src/server.py'
    august_checks[name]=hashlib.sha256(extract(august_sources[path],name).encode()).hexdigest()==expected
assert all(august_checks.values())

result=dict(reference=REF,revision=subprocess.check_output(['git','rev-parse',REF],text=True).strip(),
    kind='isolated correctness probes; not performance benchmarks',functionHashes=used,spatialPadding=actual,
    augustMainRevision=subprocess.check_output(['git','rev-parse','main'],text=True).strip(),
    sameFunctionsOnAugustMain=august_checks,
    identicalFacadesAt3m=dict(unsplitWeightedOccludedLength=original,splitIntoHalfMetreSegments=fragmented,
        conclusion='same physical facades lose all chasm penalty after segmentation'),
    oneMetreSeparatedRectangles=dict(alignmentValidatorAccepts=accepted,
        conclusion='nonintersecting bounding boxes omit the opposing room before the intended1.2m clearance ray check'))
Path(__file__).with_name('probes.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
