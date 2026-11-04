"""Observed metric vocabulary for graph growth; no prescribed lengths or turns.

Directed turns between every pair of incident edges include sums of consecutive
turns modulo one full revolution. Distinct measured values are sampled with
bounded work; counts describe current stars, values retain building observations.
"""
from collections import Counter
import math
import random

TAU=2*math.pi


def wrapped_turn(a,b):
    value=(b-a)%TAU
    return 0. if min(value,TAU-value)<1e-10 else value


class RelativeVocabulary:
    def __init__(self):
        self.lengths={};self.angles={}
        self.length_uses=Counter();self.angle_uses=Counter();self.stars={}
        self._length_keys=[];self._angle_keys=[]

    def observe(self,graph,node_ids):
        for nid in sorted(set(node_ids)):
            node=graph.nodes[nid]
            vectors=sorted((graph.nodes[m].x-node.x,graph.nodes[m].y-node.y)
                for m in graph._adj_horiz.get(nid,()))
            vectors=[v for v in vectors if math.hypot(*v)>1e-9]
            lengths=[math.hypot(*v) for v in vectors]
            bearings=[math.atan2(y,x) for x,y in vectors]
            angles=[wrapped_turn(a,b) for i,a in enumerate(bearings) for j,b in enumerate(bearings) if i!=j]
            ls=Counter(round(v,8) for v in lengths);ts=Counter(round(v,8) for v in angles)
            previous=self.stars.get(nid)
            if previous==(ls,ts):continue
            if previous:
                self.length_uses.subtract(previous[0]);self.angle_uses.subtract(previous[1])
            self.length_uses.update(ls);self.angle_uses.update(ts);self.stars[nid]=(ls,ts)
            for values,table,keys in ((lengths,self.lengths,self._length_keys),(angles,self.angles,self._angle_keys)):
                for value in values:
                    key=round(value,8)
                    if key not in table:table[key]=value;keys.append(key)

    @staticmethod
    def reference_angle(bank,node):
        """Use an observed edge in the module frame, never a compass/grid axis."""
        instance=bank.instances[node.metadata.get('root_id',node.node_id)]
        vectors=bank.graph.star_graph_offsets(node.node_id)
        if not vectors:return instance.angle
        local=min((math.atan2(y,x)-instance.angle)%(2*math.pi) for x,y in vectors)
        return instance.angle+local

    def candidates(self,bank,floor,limit=16):
        if not self._length_keys or not self._angle_keys:return []
        rng=random.Random(451+len(bank.graph.nodes)*104729+floor)
        nodes=bank.floor_nodes[floor]
        result=[];seen=set()
        for _ in range(limit*4):
            n=rng.choice(nodes)
            length=self.lengths[rng.choice(self._length_keys)]
            turn=self.angles[rng.choice(self._angle_keys)]
            bearing=self.reference_angle(bank,n)+turn
            x,y=n.x+length*math.cos(bearing),n.y+length*math.sin(bearing)
            key=(round(x,7),round(y,7))
            if key in seen:continue
            seen.add(key)
            result.append(dict(x=x,y=y,anchor_node=n.node_id,span=length,relativeAngle=turn,
                source='observed_angle_length'))
            if len(result)>=limit:break
        return result

    def summary(self):
        return dict(observedLengthCount=len(self.lengths),observedAngleCount=len(self.angles),
            angleConvention='directed_modulo_2pi',includesCompositeTurns=True)

    def export(self):
        return dict(**self.summary(),edgeLengths=sorted(self.lengths.values()),
            relativeAnglesRadians=sorted(self.angles.values()))
