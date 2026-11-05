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
    <div className="progress-heading"><div><span className="eyebrow">COMPLETED EPISODES</span><strong>Learning progress</strong></div><div className="segmented small">{['fill','reuse'].map((v)=><button key={v} className={metric===v?'active':''} onClick={()=>setMetric(v)}>{v==='fill'?'Site fill':'Independent reuse'}</button>)}</div><div className="segmented small axis-controls"><button className={axis==='episode'?'active':''} onClick={()=>setAxis('episode')}>Episodes</button><button className={axis==='time'?'active':''} disabled={!hasTime} onClick={()=>setAxis('time')}>Wall time</button></div><span className="progress-count">{records.length} recorded</span></div>
    {records.length ? <svg className="learning-chart" viewBox="0 0 710 108" preserveAspectRatio="none" role="img" aria-label={`${metric} by completed episode; blue graph estimates, green checked, red failed validation`}>
      {[.25,.5,.75].map((v)=><g key={v}><line x1="20" x2="680" y1={78-v*64} y2={78-v*64} stroke="#e0e7e2" strokeDasharray="3 4"/><text x="688" y={81-v*64} fill="#78867f" fontSize="9">{v*100}%</text></g>)}
      {selected.slice(1).map((r,i)=>r[key]!=null&&selected[i][key]!=null?<line key={i} x1={point(selected[i],i).split(',')[0]} y1={point(selected[i],i).split(',')[1]} x2={point(r,i+1).split(',')[0]} y2={point(r,i+1).split(',')[1]} stroke="#9aafa3" strokeWidth="1.4"/>:null)}
      {selected.map((r,i)=> r[key] == null ? null : <circle key={i} cx={point(r,i).split(',')[0]} cy={point(r,i).split(',')[1]} r="3.5" fill={r.valid===false||r.graphValid===false?'#b94d42':r.valid===true?'#23765a':'#4c7b9a'}><title>{r.mode} episode {r.episode} · {format(r[key]*100,1)}% · {r.valid===null?'geometry not checked':r.valid?'geometry checked':'validation failed'}</title></circle>)}
      <text x="20" y="103" fill="#78867f" fontSize="9">{axis==='time'?'0 s':`Episode ${selected[0].episode}`} </text><text x="680" y="103" textAnchor="end" fill="#78867f" fontSize="9">{axis==='time'?`${format(elapsed.at(-1)/1000,1)} s`:`Episode ${selected.at(-1).episode}`} </text>
    </svg> : <div className="chart-empty">Completed layouts will trace fill and reuse here. Validation failures stay visible.</div>}
    <div className="chart-legend"><span><i style={{background:'#4c7b9a'}}/>Graph estimate</span><span><i style={{background:'#23765a'}}/>Geometry checked</span><span><i style={{background:'#b94d42'}}/>Failed check</span><small>{axis==='time'?'Client episode wall time':'Episode order'} · estimates and checks remain distinct</small></div>
  </section>;
}
