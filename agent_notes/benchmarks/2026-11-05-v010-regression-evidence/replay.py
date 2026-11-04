import sys,random,torch,math
sys.path.insert(0,'src')
from server import ParallelTrainer
from graph_policy import GraphLearner
from graph_proxy import root_id
from shared_modules import _bounded_polygon,boundary_contact_length,turn
from tools.compare_graph_proposals import PROTOCOL
state=torch.load('agent_notes/benchmarks/2026-11-04-v010-angle-study-01/legacy-123-0.pt',weights_only=False)
learner=GraphLearner();learner.load(state)
torch.manual_seed(2024);t=ParallelTrainer(dict(PROTOCOL,graphProposalStrategy='legacy',seed=123));t.graph_learner=learner;t.set_mode('inference')
seed=500003+7*101;torch.manual_seed(seed);random.seed(seed);t.update_settings(dict(seed=seed))
for i in range(124):
 e=t.step(t.generation_id,t.episode)
 if e['type']=='episodeDone':break
bank=t.last_completed_graph.module_bank
print('audit',e['validation'])
for edge in bank.graph.edges_horiz:
 a=bank.instances[root_id(bank.graph.nodes[edge.u])];b=bank.instances[root_id(bank.graph.nodes[edge.v])]
 pa,pb=bank.shapes[a.prototype],bank.shapes[b.prototype]
 length=bank.contact(a.origin,pa,a.angle,b.origin,pb,b.angle)
 if length<bank.prior.min_contact-1e-6:
  def polygon(s,o):
   p=_bounded_polygon(tuple(((x,y),bound) for x,y,bound in s.planes),tuple(((x,y),bound) for x,y,bound in s.required),bank.prior)
   return [(o.origin[0]+turn(v,o.angle)[0],o.origin[1]+turn(v,o.angle)[1]) for v in p]
  actual=boundary_contact_length(polygon(pa,a),polygon(pb,b),a.origin,b.origin)
  print('BAD',edge.u,edge.v,'implicit',length,'actual',actual,'origins',a.origin,b.origin,'angles',a.angle,b.angle,'pids',a.prototype,b.prototype)
  print('intervals',bank._interval(pa,a.origin,a.angle,b.origin),bank._interval(pb,b.origin,b.angle,a.origin))
  print('planes A',pa.planes,'required',pa.required)
t.executor.shutdown(wait=True)
