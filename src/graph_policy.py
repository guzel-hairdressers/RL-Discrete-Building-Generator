"""Experimental trainable graph actor-critic for feasible growth actions.

A small message-passing encoder sees the current graph. Its actor chooses among
validated proposals; it is not trained to imitate the reference search ranking.
The episode objective is explicitly experimental, not a calibrated design score.
"""
from __future__ import annotations
import math
import torch
from torch import nn
from torch.distributions import Categorical


class GraphActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.node = nn.Sequential(nn.Linear(8,32),nn.SiLU())
        self.message = nn.Sequential(nn.Linear(33,32),nn.SiLU())
        self.update = nn.Sequential(nn.Linear(64,32),nn.SiLU())
        self.actor = nn.Sequential(nn.Linear(42,64),nn.SiLU(),nn.Linear(64,1))
        self.critic = nn.Sequential(nn.Linear(32,32),nn.SiLU(),nn.Linear(32,1))

    def forward(self,nodes,edges,lengths,candidates):
        h=self.node(nodes)
        for _ in range(2):
            messages=torch.zeros_like(h)
            degree=torch.zeros((len(h),1),device=h.device)
            if edges.numel():
                src,dst=edges
                messages.index_add_(0,dst,self.message(torch.cat((h[src],lengths),dim=1)))
                degree.index_add_(0,dst,torch.ones_like(lengths))
            h=self.update(torch.cat((h,messages/degree.clamp_min(1)),dim=1))
        context=h.mean(0)
        logits=self.actor(torch.cat((context.expand(len(candidates),-1),candidates),dim=1)).squeeze(-1)
        return logits,self.critic(context).squeeze(-1)


def encode_graph(graph,device):
    rows=list(graph.nodes.values()); ids={n.node_id:i for i,n in enumerate(rows)}
    cx=sum(n.x for n in rows)/len(rows);cy=sum(n.y for n in rows)/len(rows)
    radius=getattr(getattr(graph,'size_prior',None),'radius',4.5)
    features=[]
    for n in rows:
        role=n.cell_type.value
        features.append([float(role=='room'),float(role=='core'),float(role=='void'),
            float(n.scope.value=='multi_floor'),len(graph._adj_horiz.get(n.node_id,()))/8,
            math.hypot(n.x-cx,n.y-cy)/(10*radius),n.area/(4*radius*radius),n.floor_index/max(1,graph.num_floors-1)])
    pairs=[];lengths=[]
    for e in graph.edges_horiz+graph.edges_vert:
        a,b=graph.nodes[e.u],graph.nodes[e.v]
        length=math.dist(a.pos3d,b.pos3d)/(2*radius)
        for u,v in ((e.u,e.v),(e.v,e.u)):
            pairs.append([ids[u],ids[v]]);lengths.append([length])
    edges=torch.tensor(pairs,dtype=torch.long,device=device).reshape(-1,2).T
    return (torch.tensor(features,dtype=torch.float32,device=device),edges,
            torch.tensor(lengths,dtype=torch.float32,device=device).reshape(-1,1))


class GraphLearner:
    def __init__(self,device='cpu',seed=123,lr=.001):
        self.device=torch.device(device)
        # Separate initialization/sampling RNG preserves legacy-policy reproducibility.
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self.model=GraphActorCritic().to(self.device)
        self.optimizer=torch.optim.Adam(self.model.parameters(),lr=lr)
        self.rng=torch.Generator(device='cpu').manual_seed(seed)
        self.updates=0
        self.last={}
        self.clear_episode()

    def clear_episode(self): self.trajectory=[]

    def choose(self,graph,features,training=True):
        with torch.set_grad_enabled(training):
            logits,value=self.model(*encode_graph(graph,self.device),
                torch.tensor(features,dtype=torch.float32,device=self.device))
            distribution=Categorical(logits=logits)
            index=int(torch.multinomial(distribution.probs.detach().cpu(),1,generator=self.rng)) if training else int(logits.argmax())
            if training:
                self.trajectory.append((distribution.log_prob(torch.tensor(index,device=self.device)),value,distribution.entropy(),len(features)))
        return index

    def finish(self,reward,training=True):
        if not math.isfinite(reward): self.clear_episode(); raise ValueError('nonfinite graph reward')
        stats=dict(policyLoss=0.,actorLoss=0.,valueLoss=0.,policyEntropy=0.,gradientNorm=0.,
            advantage=0.,policyUpdateCount=self.updates,policyDecisionCount=len(self.trajectory),
            learningAlgorithm='graph_actor_critic_experimental' if training else 'graph_inference',
            learningRate=self.optimizer.param_groups[0]['lr'] if training else 0.,trainingReward=reward)
        if training and self.trajectory:
            returns=torch.tensor([reward*.99**(len(self.trajectory)-1-i) for i in range(len(self.trajectory))],device=self.device)
            logs,values,entropies,counts=zip(*self.trajectory)
            values=torch.stack(values); advantages=returns-values
            # No centering across actions: constant-return episodes still train the value baseline.
            actor=-(torch.stack(logs)*advantages.detach()).mean()
            critic=torch.nn.functional.smooth_l1_loss(values,returns)
            entropy=torch.stack(entropies).mean()
            loss=actor+.5*critic-.01*entropy
            if not torch.isfinite(loss): self.clear_episode();raise ValueError('nonfinite graph loss')
            self.optimizer.zero_grad(set_to_none=True);loss.backward()
            norm=nn.utils.clip_grad_norm_(self.model.parameters(),2.,error_if_nonfinite=True)
            self.optimizer.step();self.updates+=1
            stats.update(policyLoss=float(loss.detach()),actorLoss=float(actor.detach()),valueLoss=float(critic.detach()),
                policyEntropy=float(entropy.detach()),gradientNorm=float(norm),advantage=float(advantages.detach().mean()),policyUpdateCount=self.updates,
                stochasticDecisionCount=sum(c>1 for c in counts))
        self.clear_episode();self.last=stats
        return stats

    def state(self):
        return dict(schema=1,model={k:v.detach().cpu().clone() for k,v in self.model.state_dict().items()},
            optimizer=self.optimizer.state_dict(),rng=self.rng.get_state(),updates=self.updates)

    def load(self,state):
        if not isinstance(state,dict) or state.get('schema')!=1: raise ValueError('unsupported graph policy checkpoint')
        if type(state.get('updates')) is not int or state['updates']<0: raise ValueError('invalid graph update count')
        self.model.load_state_dict(state['model'],strict=True)
        self.optimizer.load_state_dict(state['optimizer'])
        self.rng.set_state(state['rng']);self.updates=state['updates'];self.clear_episode()
