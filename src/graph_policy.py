"""Experimental trainable graph actor-critic for feasible growth actions.

A small message-passing encoder sees the current graph. Its actor chooses among
graph-screened proposals; it is not trained to imitate the reference search ranking.
The episode objective is explicitly experimental, not a calibrated design score.
"""
from __future__ import annotations
import math
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical,Normal


ARCHITECTURES = ('pooled', 'message_passing', 'local_message_passing', 'candidate_attention')


def outcome_reward(score, valid):
    if not math.isfinite(score): raise ValueError('nonfinite graph score')
    return math.tanh(score / 100.) if valid else -1.


class GraphActorCritic(nn.Module):
    def __init__(self, architecture='message_passing'):
        super().__init__()
        if architecture not in ARCHITECTURES: raise ValueError('unknown graph architecture')
        self.architecture=architecture
        self.node = nn.Sequential(nn.Linear(8,32),nn.SiLU())
        self.message = nn.Sequential(nn.Linear(33,32),nn.SiLU())
        self.update = nn.Sequential(nn.Linear(64,32),nn.SiLU())
        self.actor = nn.Sequential(nn.Linear(76 if architecture in ('local_message_passing','candidate_attention') else 44,64),nn.SiLU(),nn.Linear(64,1))
        self.critic = nn.Sequential(nn.Linear(32,32),nn.SiLU(),nn.Linear(32,1))
        if architecture=='candidate_attention':
            self.attention=nn.Sequential(nn.Linear(37,32),nn.SiLU(),nn.Linear(32,1))

        # Continuous proposals use the same graph/anchor embeddings as selection.
        self.proposal=nn.Sequential(nn.Linear(66,32),nn.SiLU(),nn.Linear(32,4))
        # New relation/role features start with zero influence on old policies.
        self.spatial=nn.Sequential(nn.Linear(6,32),nn.SiLU(),nn.Linear(32,1))
        nn.init.zeros_(self.spatial[-1].weight);nn.init.zeros_(self.spatial[-1].bias)
        self.plot_encoder=nn.Sequential(nn.Linear(8,32),nn.SiLU(),nn.Linear(32,32))
        self.plot_actor=nn.Sequential(nn.Linear(8,32),nn.SiLU(),nn.Linear(32,1))
        for head in (self.plot_encoder,self.plot_actor):
            nn.init.zeros_(head[-1].weight);nn.init.zeros_(head[-1].bias)

    def encode(self,nodes,edges,lengths,plot=None):
        h=self.node(nodes)
        if plot is not None:h=h+self.plot_encoder(plot)
        for _ in range(2):
            messages=torch.zeros_like(h)
            degree=torch.zeros((len(h),1),device=h.device)
            if edges.numel() and self.architecture!='pooled':
                src,dst=edges
                messages.index_add_(0,dst,self.message(torch.cat((h[src],lengths),dim=1)))
                degree.index_add_(0,dst,torch.ones_like(lengths))
            h=self.update(torch.cat((h,messages/degree.clamp_min(1)),dim=1))
        return h,h.mean(0)

    def forward(self,nodes,edges,lengths,candidates,anchors=None,geometry=None,encoded=None,plot=None):
        h,context=self.encode(nodes,edges,lengths) if encoded is None else encoded
        if candidates.shape[-1]==10:
            candidates=torch.nn.functional.pad(candidates,(0,2))
        spatial=candidates[:,12:] if candidates.shape[-1]>12 else None
        candidates=candidates[:,:12]
        parts=[context.expand(len(candidates),-1),candidates]
        if self.architecture=='local_message_passing':
            if anchors is None: raise ValueError('local graph actor requires candidate anchors')
            parts.append(h[anchors])
        if self.architecture=='candidate_attention':
            if geometry is None: raise ValueError('candidate attention requires relative geometry')
            nodes=h.expand(len(candidates),-1,-1)
            scope=candidates[:,0,None,None].expand(-1,len(h),1)
            energies=self.attention(torch.cat((nodes,geometry,scope),dim=-1)).squeeze(-1)
            parts.append((energies.softmax(dim=1).unsqueeze(-1)*nodes).sum(dim=1))
        logits=self.actor(torch.cat(parts,dim=1)).squeeze(-1)
        if spatial is not None:logits=logits+self.spatial(spatial).squeeze(-1)
        if plot is not None:logits=logits+self.plot_actor(plot).squeeze(-1)
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
    pairs,lengths=_edge_arrays(graph,ids,radius)
    # NumPy packs numeric lists without PyTorch's recursive scalar conversion.
    # Keep the original Python calculations and ordering bit-for-bit.
    edges=torch.from_numpy(pairs).to(device).T
    return (torch.from_numpy(np.asarray(features,dtype=np.float32)).to(device),edges,
            torch.from_numpy(lengths).to(device))


def _edge_arrays(graph,ids,radius):
    """Append-only growth packs only new edges; poses/order invalidate exactly.

    Allocate new arrays on append: prior action tapes may retain old tensors.
    Never mutate arrays already consumed by an autograd computation.
    """
    key=(radius,getattr(graph,'pose_revision',0),tuple(ids))
    cache=getattr(graph,'_policy_edges',None)
    valid=cache is not None and cache['radius_pose']==key[:2] and key[2][:len(cache['ids'])]==cache['ids']
    if not valid:cache={'radius_pose':key[:2],'ids':(),'groups':{}}
    cache['ids']=key[2];groups=[]
    for name,edges in (('horizontal',graph.edges_horiz),('vertical',graph.edges_vert)):
        previous=cache['groups'].get(name)
        if previous is not None and (len(edges)<previous[0] or (previous[0] and edges[previous[0]-1] is not previous[1])):previous=None
        start=previous[0] if previous else 0;pairs=[];lengths=[]
        for edge in edges[start:]:
            a,b=graph.nodes[edge.u],graph.nodes[edge.v]
            length=math.dist(a.pos3d,b.pos3d)/(2*radius)
            pairs.extend(((ids[edge.u],ids[edge.v]),(ids[edge.v],ids[edge.u])));lengths.extend((length,length))
        p=np.asarray(pairs,dtype=np.int64).reshape(-1,2);v=np.asarray(lengths,dtype=np.float32).reshape(-1,1)
        if previous is not None:
            p=np.concatenate((previous[2],p)) if len(p) else previous[2]
            v=np.concatenate((previous[3],v)) if len(v) else previous[3]
        result=(len(edges),edges[-1] if edges else None,p,v);cache['groups'][name]=result;groups.append(result)
    graph._policy_edges=cache
    return np.concatenate([g[2] for g in groups]),np.concatenate([g[3] for g in groups])


def relative_candidate_geometry(graph,anchors,positions,device):
    """Geometry in each proposed action's own frame; no absolute compass/grid axes."""
    rows=list(graph.nodes.values())
    points=torch.tensor([[n.x,n.y] for n in rows],dtype=torch.float32,device=device)
    candidates=torch.tensor(positions,dtype=torch.float32,device=device)
    direction=candidates-points[anchors]
    direction=direction/direction.norm(dim=1,keepdim=True).clamp_min(1e-8)
    normal=torch.stack((-direction[:,1],direction[:,0]),dim=1)
    delta=points[None,:,:]-candidates[:,None,:]
    scale=2*getattr(getattr(graph,'size_prior',None),'radius',4.5)
    along=(delta*direction[:,None,:]).sum(-1)/scale
    across=(delta*normal[:,None,:]).sum(-1)/scale
    distance=delta.norm(dim=-1)/scale
    floors=torch.tensor([n.floor_index for n in rows],dtype=torch.float32,device=device)
    vertical=(floors[None,:]-floors[anchors,None])/max(1,graph.num_floors-1)
    return torch.stack((along,across,distance,vertical),dim=-1)


class GraphLearner:
    def __init__(self,device='cpu',seed=123,lr=.001,architecture='message_passing'):
        self.device=torch.device(device)
        # Separate initialization/sampling RNG preserves legacy-policy reproducibility.
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self.model=GraphActorCritic(architecture).to(self.device)
        self.optimizer=torch.optim.Adam(self.model.parameters(),lr=lr)
        self.rng=torch.Generator(device='cpu').manual_seed(seed)
        self.updates=0
        self.last={}
        self.clear_episode()

    def clear_episode(self):
        self.trajectory=[];self._prepared=None
        self.proposal_count=0;self.proposal_decisions=0
        self.selected_sources={};self.selected_factors={}

    def _prepare(self,graph):
        key=(id(graph),len(graph.nodes),torch.is_grad_enabled())
        if self._prepared is None or self._prepared[0]!=key:
            tensors=encode_graph(graph,self.device)
            plot=None
            if getattr(graph,'spatial_settings',{}).get('graphPlotDirections',True):
                from plot_directions import features
                plot=torch.tensor([features(graph,n.floor_index,n.pos2d,n.pos2d,n.orientation)
                                   for n in graph.nodes.values()],dtype=torch.float32,device=self.device)
            self._prepared=(key,tensors,self.model.encode(*tensors,plot))
        return self._prepared[1:]

    def propose_continuous(self,bank,floor,training=True,limit=4,min_distance=2.5,use_vocabulary=False):
        import random
        from relative_vocabulary import RelativeVocabulary
        nodes=list(bank.floor_nodes[floor])
        selection_rng=random.Random(194+len(bank.graph.nodes)*104729+floor)
        selection_rng.shuffle(nodes)
        nodes=[nodes[i%len(nodes)] for i in range(limit)] if nodes else []
        span_range=2*bank.prior.radius-min_distance
        if not nodes or span_range<=1e-8:return []
        # Reuse either factor independently: a new angle need not invent a new
        # length. Continuous lengths almost never hit an existing contact length
        # at numeric tolerance, so coupling both factors prevented useful reuse.
        fixed_turns={};fixed_lengths={}
        if use_vocabulary:
            for i in range(len(nodes)):
                if i%3==0 and bank.vocabulary._length_keys:
                    fixed_lengths[i]=bank.vocabulary.lengths[selection_rng.choice(bank.vocabulary._length_keys)]
                elif i%3==1 and bank.vocabulary._angle_keys:
                    fixed_turns[i]=bank.vocabulary.angles[selection_rng.choice(bank.vocabulary._angle_keys)]
        with torch.set_grad_enabled(training):
            tensors,(h,context)=self._prepare(bank.graph)
            ids={nid:i for i,nid in enumerate(bank.graph.nodes)}
            anchors=torch.tensor([ids[n.node_id] for n in nodes],device=self.device)
            summary=bank.vocabulary.summary()
            vocab=h.new_tensor([math.log1p(summary['observedLengthCount']),math.log1p(summary['observedAngleCount'])]).expand(len(nodes),-1)
            parameters=self.model.proposal(torch.cat((context.expand(len(nodes),-1),h[anchors],vocab),dim=1))
            mean,log_std=parameters[:,:2],parameters[:,2:].clamp(-3.,1.)
            distribution=Normal(mean,log_std.exp())
            free=torch.ones_like(mean)
            for i in fixed_turns:free[i,0]=0.
            for i in fixed_lengths:free[i,1]=0.
            if training:
                noise=torch.randn(mean.shape,generator=self.rng).to(self.device)
                sample=mean+log_std.exp()*noise
                latent=sample.detach()
                def log_jacobian(z):
                    angular=math.log(math.pi)+2*(math.log(2.)-z[:,0]-torch.nn.functional.softplus(-2*z[:,0]))
                    length=math.log(span_range)+torch.nn.functional.logsigmoid(z[:,1])+torch.nn.functional.logsigmoid(-z[:,1])
                    return torch.stack((angular,length),dim=1)
                # Entropy is for physical angle/length, including the nonlinear
                # transform; latent variance cannot earn entropy by saturation.
                entropy=((distribution.entropy()+log_jacobian(sample))*free).sum(-1).mean()
                # All latent proposals are stochastic actions, including rejected
                # ones. Credit the joint proposal draw, not just accepted samples.
                self.trajectory.append((((distribution.log_prob(latent)-log_jacobian(latent))*free).sum(),self.model.critic(context).squeeze(-1),
                    entropy,1))
            else:
                # Frozen inference searches the learned distribution with a
                # reproducible noise bank. No learned angle is snapped to a grid.
                rng=torch.Generator(device='cpu').manual_seed(871+len(bank.graph.nodes)*104729+floor)
                noise=torch.randn(mean.shape,generator=rng).to(self.device)
                latent=(mean+log_std.exp()*noise).detach()
            self.proposal_count+=len(nodes);self.proposal_decisions+=1
            relative=(math.pi*latent[:,0].tanh()).cpu().tolist()
            spans=(min_distance+(2*bank.prior.radius-min_distance)*latent[:,1].sigmoid()).cpu().tolist()
        result=[]
        for i,(n,turn,span) in enumerate(zip(nodes,relative,spans)):
            turn=fixed_turns.get(i,turn);span=fixed_lengths.get(i,span)
            bearing=RelativeVocabulary.reference_angle(bank,n)+turn
            result.append(dict(x=n.x+span*math.cos(bearing),y=n.y+span*math.sin(bearing),
                anchor_node=n.node_id,span=span,relativeAngle=turn,source='neural_continuous',
                angleSource='observed' if i in fixed_turns else 'neural',
                lengthSource='observed' if i in fixed_lengths else 'neural'))
        return result

    def choose(self,graph,features,training=True,anchors=None,positions=None,sources=None,factor_sources=None):
        ids={nid:i for i,nid in enumerate(graph.nodes)}
        anchor_indices=torch.tensor([ids[a] for a in anchors],dtype=torch.long,device=self.device) if anchors is not None else None
        geometry=None
        if self.model.architecture=='candidate_attention':
            if positions is None or anchors is None: raise ValueError('candidate attention needs poses and anchors')
            geometry=relative_candidate_geometry(graph,anchor_indices,positions,self.device)
        with torch.set_grad_enabled(training):
            tensors,encoded=self._prepare(graph)
            plot=None
            if anchors is not None and positions is not None and getattr(graph,'spatial_settings',{}).get('graphPlotDirections',True):
                from plot_directions import features as plot_features
                plot=torch.tensor([plot_features(graph,graph.nodes[a].floor_index,graph.nodes[a].pos2d,p)
                                   for a,p in zip(anchors,positions)],dtype=torch.float32,device=self.device)
            logits,value=self.model(*tensors,
                torch.tensor(features,dtype=torch.float32,device=self.device),
                anchor_indices,geometry,encoded=encoded,plot=plot)
            distribution=Categorical(logits=logits)
            index=int(torch.multinomial(distribution.probs.detach().cpu(),1,generator=self.rng)) if training else int(logits.argmax())
            if training:
                self.trajectory.append((distribution.log_prob(torch.tensor(index,device=self.device)),value,distribution.entropy(),len(features)))
            if sources:
                source=sources[index];self.selected_sources[source]=self.selected_sources.get(source,0)+1
            if factor_sources:
                key='/'.join(factor_sources[index]);self.selected_factors[key]=self.selected_factors.get(key,0)+1
        # Reuse the embedding for proposal generation + selection only; callers
        # may mutate existing nodes without changing their count between choices.
        self._prepared=None
        return index

    def finish(self,reward,training=True):
        if not math.isfinite(reward): self.clear_episode(); raise ValueError('nonfinite graph reward')
        stats=dict(policyLoss=0.,actorLoss=0.,valueLoss=0.,policyEntropy=0.,gradientNorm=0.,
            advantage=0.,policyUpdateCount=self.updates,policyDecisionCount=len(self.trajectory),
            learningAlgorithm='graph_actor_critic_experimental' if training else 'graph_inference',
            architecture=self.model.architecture,
            learningRate=self.optimizer.param_groups[0]['lr'] if training else 0.,trainingReward=reward,
            continuousProposalCount=self.proposal_count,continuousProposalDecisions=self.proposal_decisions,
            selectedProposalSources=dict(self.selected_sources),selectedFactorSources=dict(self.selected_factors))
        if training and self.trajectory:
            # This is one completed-design objective, independent of how many
            # decisions were used to construct it. Do not reward delaying failure.
            returns=torch.full((len(self.trajectory),),float(reward),device=self.device)
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
        return dict(schema=5,architecture=self.model.architecture,model={k:v.detach().cpu().clone() for k,v in self.model.state_dict().items()},
            optimizer=self.optimizer.state_dict(),rng=self.rng.get_state(),updates=self.updates)

    def load(self,state):
        if not isinstance(state,dict) or state.get('schema') not in (1,2,3,4,5):
            raise ValueError('unsupported graph policy checkpoint')
        architecture=state.get('architecture','message_passing')
        if architecture not in ARCHITECTURES: raise ValueError('unknown graph architecture')
        if type(state.get('updates')) is not int or state['updates']<0:
            raise ValueError('invalid graph update count')
        # Prepare a fresh model/optimizer; rejected checkpoints cannot partially mutate a learner.
        candidate=GraphLearner(self.device,lr=self.optimizer.param_groups[0]['lr'],architecture=architecture)
        import copy
        model_state=copy.deepcopy(state['model'])
        optimizer_state=copy.deepcopy(state['optimizer'])
        if state['schema']<3:
            # Preserve old encoder/actor/critic and Adam moments. New source
            # features start at zero influence; the proposal head starts fresh.
            def widen(value):
                result=value.new_zeros((value.shape[0],value.shape[1]+2))
                result[:,:42]=value[:,:42];result[:,44:]=value[:,42:]
                return result
            weight=model_state.get('actor.0.weight')
            migrated=weight is not None and weight.shape[1] in (42,74)
            if migrated:model_state['actor.0.weight']=widen(weight)
            expected=candidate.model.state_dict()
            for key,value in expected.items():
                if key.startswith('proposal.') and key not in model_state:model_state[key]=value
            group=optimizer_state['param_groups'][0]
            new_ids=candidate.optimizer.state_dict()['param_groups'][0]['params']
            if len(group['params'])<len(new_ids):
                old_ids=group['params'];group['params']=new_ids
                actor_index=list(dict(candidate.model.named_parameters())).index('actor.0.weight')
                actor_id=old_ids[actor_index]
                if migrated and actor_id in optimizer_state['state']:
                    for key,value in optimizer_state['state'][actor_id].items():
                        if isinstance(value,torch.Tensor) and value.ndim==2:
                            optimizer_state['state'][actor_id][key]=widen(value)
        if state['schema']<4:
            for key,value in candidate.model.state_dict().items():
                if key.startswith('spatial.') and key not in model_state:model_state[key]=value
            optimizer_state['param_groups'][0]['params']=candidate.optimizer.state_dict()['param_groups'][0]['params']
        if state['schema']<5:
            for key,value in candidate.model.state_dict().items():
                if key.startswith(('plot_encoder.','plot_actor.')) and key not in model_state:model_state[key]=value
            optimizer_state['param_groups'][0]['params']=candidate.optimizer.state_dict()['param_groups'][0]['params']
        candidate.model.load_state_dict(model_state,strict=True)
        candidate.optimizer.load_state_dict(optimizer_state)
        candidate.rng.set_state(state['rng'])
        self.model=candidate.model;self.optimizer=candidate.optimizer
        self.rng=candidate.rng;self.updates=state['updates'];self.clear_episode()
