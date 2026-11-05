import React, { useEffect, useRef, useState } from 'react';
import { useStore } from '../store/useStore';
import { format } from '../store/presentation';

const HEIGHT = 174;
const LABELS={fill:'Site fill',reuse:'Independent reuse',exposure:'Livable facade access proxy'};
const MARGIN = { left: 37, right: 39, top: 15, bottom: 29 };
const finite = (value) => value != null && Number.isFinite(Number(value));

export function RewardTrendChart() {
  const records = useStore((s) => s.episodeRecords);
  const [metric, setMetric] = useState('fill');
  const [axis, setAxis] = useState('episode');
  const plot = useRef(null);
  const [width, setWidth] = useState(700);

  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(180, Math.round(entry.contentRect.width)));
    });
    observer.observe(plot.current);
    return () => observer.disconnect();
  }, []);

  const selected = records.slice(-80);
  const hasTime = selected.length > 0 && selected.every((r) => finite(r.wallMs));
  const timeAxis = axis === 'time' && hasTime;
  let total = 0;
  const elapsed = selected.map((r) => (total += finite(r.wallMs) ? Number(r.wallMs) : 0));
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (i) => MARGIN.left + (selected.length === 1 ? .5 : timeAxis
    ? (elapsed[i] - elapsed[0]) / Math.max(1, elapsed.at(-1) - elapsed[0])
    : i / Math.max(1, selected.length - 1)) * plotWidth;
  const y = (value) => MARGIN.top + (1 - Number(value)) * plotHeight;
  const state = (r) => r.valid === false || r.graphValid === false || r.spatialRequirementsMet === false ? 'failed' : r.valid === true ? 'checked' : 'estimate';
  const describe = (r) => r.spatialRequirementsMet === false ? 'Spatial proxy requirements unmet' : r.valid === false ? 'Geometry validation failed' : r.graphValid === false
    ? 'Graph check failed; geometry not checked' : r.valid === true ? 'Geometry checked' : 'Graph estimate; geometry not checked';
  const coordinate = (r, i) => `${x(i)},${y(r[metric])}`;
  // Keep the complete observed sequence connected, including failed checks.
  // Only an unavailable measurement creates a gap; crosses retain failure status.
  const segments = [];
  let segment = [];
  selected.forEach((r, i) => {
    if (!finite(r[metric])) {
      if (segment.length > 1) segments.push(segment.join(' '));
      segment = [];
    } else segment.push(coordinate(r, i));
  });
  if (segment.length > 1) segments.push(segment.join(' '));
  const tickIndices = [...new Set([0, Math.floor((selected.length - 1) / 2), selected.length - 1])].filter((i) => i >= 0);
  const hasValues = selected.some((r) => finite(r[metric]));

  return <section className="progress-panel">
    <div className="progress-heading">
      <div><span className="eyebrow">Activity</span><strong>Learning progress</strong></div>
      <div className="segmented small">{['fill', 'reuse', 'exposure'].map((v) => <button key={v} className={metric === v ? 'active' : ''} onClick={() => setMetric(v)}>{LABELS[v]}</button>)}</div>
      <div className="segmented small axis-controls">
        <button className={!timeAxis ? 'active' : ''} onClick={() => setAxis('episode')}>Episodes</button>
        <button className={timeAxis ? 'active' : ''} disabled={!hasTime} onClick={() => setAxis('time')}>Wall time</button>
      </div>
      <span className="progress-count">{records.length > 80 ? 'Latest 80 · ' : ''}{records.length} recorded</span>
    </div>
    <div className="learning-plot" ref={plot}>
      {hasValues ? <svg className="learning-chart" viewBox={`0 0 ${width} ${HEIGHT}`} role="img" aria-label={`${LABELS[metric]} from 0 to 100 percent by ${timeAxis ? 'active client time (pauses excluded)' : 'completed episode'}. Hollow dots: graph estimates. Solid dots: checked geometry. Crosses: failed checks.`}>
        <defs><clipPath id="learning-plot-clip"><rect x={MARGIN.left - 4} y={MARGIN.top - 4} width={plotWidth + 8} height={plotHeight + 8}/></clipPath></defs>
        {[0, .25, .5, .75, 1].map((v) => <g key={v}>
          <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(v)} y2={y(v)} stroke={v === 0 ? '#dedede' : '#efefef'} strokeDasharray={v === 0 ? undefined : '3 5'}/>
          <text x={MARGIN.left - 9} y={y(v)} dominantBaseline="middle" textAnchor="end" fill="#999" fontSize="10">{v * 100}%</text>
          <text x={width - MARGIN.right + 9} y={y(v)} dominantBaseline="middle" textAnchor="start" fill="#999" fontSize="10">{v * 100}%</text>
        </g>)}
        <g clipPath="url(#learning-plot-clip)">
          {segments.map((points, i) => <polyline key={i} points={points} fill="none" stroke="#b4b4b4" strokeWidth="1.2" strokeLinejoin="round"/>)}
          {selected.map((r, i) => {
            if (!finite(r[metric])) return null;
            const px = x(i), py = y(r[metric]);
            return <g key={i} className="learning-observation">
              <title>{`${r.mode} · Episode ${r.episode} · ${format(Number(r[metric]) * 100, 1)}%\n${describe(r)}`}</title>
              <circle cx={px} cy={py} r="7" fill="transparent"/>
              {state(r) === 'failed'
                ? <path d={`M${px - 2.5},${py - 2.5}l5,5m-5,0l5,-5`} stroke="#555" strokeWidth="1.2" fill="none"/>
                : <circle cx={px} cy={py} r="2.7" fill={state(r) === 'checked' ? '#333' : '#fff'} stroke={state(r) === 'checked' ? '#333' : '#888'} strokeWidth="1.1"/>}
            </g>;
          })}
        </g>
        {tickIndices.map((i) => <text key={i} x={x(i)} y={HEIGHT - 7} textAnchor={selected.length === 1 ? 'middle' : i === 0 ? 'start' : i === selected.length - 1 ? 'end' : 'middle'} fill="#999" fontSize="10">{timeAxis ? `${format((elapsed[i] - elapsed[0]) / 1000, 1)} s` : `Ep ${selected[i].episode}`}</text>)}
      </svg> : <div className="chart-empty">{records.length ? 'This metric has not been measured yet.' : 'Completed layouts will trace fill, reuse and livable facade access here.'}</div>}
    </div>
    <div className="chart-legend">
      <span><i className="estimate-symbol"/>Graph estimate</span><span><i className="checked-symbol"/>Geometry checked</span><span><i className="failed-symbol"/>Failed check</span>
      <small>{timeAxis ? 'Active run time since first visible result; pauses excluded' : 'Completed episodes'} · hover a point for details</small>
    </div>
  </section>;
}
