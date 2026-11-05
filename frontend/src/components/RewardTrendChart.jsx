import React, { useState } from 'react';
import { useStore } from '../store/useStore';
import { format } from '../store/presentation';
export function RewardTrendChart() {
  const records=useStore((s)=>s.episodeRecords);
  const [metric,setMetric]=useState('fill');
  const [axis,setAxis]=useState('episode');
  const selected=records.slice(-80), key=metric==='reuse'?'reuse':'fill';
  const hasTime=selected.length>0 && selected.every((r)=>r.wallMs!=null);
  const elapsed=selected.map((_,i)=>selected.slice(0,i+1).reduce((sum,r)=>sum+(r.wallMs ?? 0),0));
  const point=(r,i)=>`${20+(axis==='time' ? elapsed[i]/Math.max(1,elapsed.at(-1)) : i/Math.max(1,selected.length-1))*660},${78-(Number(r[key])||0)*64}`;
  return <section className="progress-panel">
    <div className="progress-heading"><div><span className="eyebrow">Activity</span><strong>Learning progress</strong></div><div className="segmented small">{['fill','reuse'].map((v)=><button key={v} className={metric===v?'active':''} onClick={()=>setMetric(v)}>{v==='fill'?'Site fill':'Independent reuse'}</button>)}</div><div className="segmented small axis-controls"><button className={axis==='episode'?'active':''} onClick={()=>setAxis('episode')}>Episodes</button><button className={axis==='time'?'active':''} disabled={!hasTime} onClick={()=>setAxis('time')}>Wall time</button></div><span className="progress-count">{records.length} recorded</span></div>
    {records.length ? <svg className="learning-chart" viewBox="0 0 710 108" preserveAspectRatio="none" role="img" aria-label={`${metric} by completed episode; hollow circles show graph estimates, solid circles show checked geometry, crosses show failed validation`}>
      {[.25,.5,.75].map((v)=><g key={v}><line x1="20" x2="680" y1={78-v*64} y2={78-v*64} stroke="#eaeaea" strokeDasharray="3 4"/><text x="688" y={81-v*64} fill="#9b9b9b" fontSize="9">{v*100}%</text></g>)}
      {selected.slice(1).map((r,i)=>r[key]!=null&&selected[i][key]!=null?<line key={i} x1={point(selected[i],i).split(',')[0]} y1={point(selected[i],i).split(',')[1]} x2={point(r,i+1).split(',')[0]} y2={point(r,i+1).split(',')[1]} stroke="#bdbdbd" strokeWidth="1.4"/>:null)}
      {selected.map((r,i)=> {
        if (r[key] == null) return null;
        const [x,y]=point(r,i).split(',').map(Number), failed=r.valid===false || r.graphValid===false;
        return <g key={i}><title>{r.mode} episode {r.episode} · {format(r[key]*100,1)}% · {r.valid===null?'geometry not checked':r.valid?'geometry checked':'validation failed'}</title>{failed ? <path d={`M${x-3},${y-3}l6,6m-6,0l6,-6`} fill="none" stroke="#333" strokeWidth="1.5"/> : <circle cx={x} cy={y} r="3.5" fill={r.valid===true?'#333':'#fff'} stroke={r.valid===true?'#333':'#888'} strokeWidth="1.2"/>}</g>;
      })}
      <text x="20" y="103" fill="#9b9b9b" fontSize="9">{axis==='time'?'0 s':`Episode ${selected[0].episode}`} </text><text x="680" y="103" textAnchor="end" fill="#9b9b9b" fontSize="9">{axis==='time'?`${format(elapsed.at(-1)/1000,1)} s`:`Episode ${selected.at(-1).episode}`} </text>
    </svg> : <div className="chart-empty">Completed layouts will trace fill and reuse here. Validation failures stay visible.</div>}
    <div className="chart-legend"><span><i className="estimate-symbol"/>Graph estimate</span><span><i className="checked-symbol"/>Geometry checked</span><span><i className="failed-symbol"/>Failed check</span><small>{axis==='time'?'Client episode wall time':'Episode order'} · estimates and checks remain distinct</small></div>
  </section>;
}
