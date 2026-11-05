import React, { useEffect, useState } from 'react';
import { X, SlidersHorizontal, ArrowRight, CheckCircle2, AlertCircle } from 'lucide-react';
import { useDialogFocus } from './useDialogFocus';
import { useStore } from '../store/useStore';
import { areaMetrics, format, percent, moduleColor, moduleInventory, validationLabel } from '../store/presentation';

export function OutcomeStrip() {
  const { metrics: m, validation, graphState, settings, dictionary, hasSite, individualPlacementsList } = useStore();
  const areas = areaMetrics(m, validation, graphState?.realized ? individualPlacementsList : []);
  const audit = m.reuseAudit;
  const measured = graphState?.realized;
  const title = !hasSite ? 'Waiting for optimizer' : measured ? 'Realized measurements' : 'Graph constraint estimates';
  const types = audit?.prototypeCount ?? (graphState ? moduleInventory(graphState.nodes, dictionary).length : m.vocabSize);
  return <section className="outcome-strip" aria-label="Layout outcomes">
    <div className="measurement-source"><span className="eyebrow">Overview</span><strong>{title}</strong><span className={`validation-pill ${validation?.valid === true ? 'valid' : validation?.valid === false ? 'invalid' : ''}`}>{validation?.valid === true ? <CheckCircle2 size={12}/> : <AlertCircle size={12}/>} {validationLabel(validation)}</span></div>
    <div className="outcome"><span>Site fill</span><strong>{percent(m.fillRatio)}</strong><small>{format(areas.filled)} m² filled</small></div>
    <div className="outcome"><span>Residential area</span><strong>{format(areas.residential)}<em> m²</em></strong><small>{percent(m.rentableRatio)} of filled area · circulation {areas.circulation == null ? 'unmeasured' : `${format(areas.circulation)} m²`}</small></div>
    <div className="outcome"><span>Independent reuse</span><strong>{percent(audit?.independentRepeatFraction)}</strong><small>{format(audit?.independentOccurrences)} independent occurrences</small></div>
    <div className="outcome"><span>Module types</span><strong>{format(types)}<em> / {m.dictionaryMaxTypes ?? settings.graphMaxTypes ?? 15}</em></strong><small>{m.dictionaryTargetTypes ?? settings.dictCap ?? 10} soft target · {format(audit?.verticalCopies)} floor copies</small></div>
  </section>;
}

function Shape({ shape, id }) {
  const poly = shape?.poly || shape?.polygon || [];
  if (poly.length < 3) return <span className="constraint-glyph" style={{ color: moduleColor(id) }}>⌗</span>;
  const pts = poly.map((p) => [p.x ?? p[0], -(p.y ?? p[1])]);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x = Math.min(...xs), y = Math.min(...ys), w = Math.max(...xs) - x, h = Math.max(...ys) - y;
  return <svg viewBox={`${x-1} ${y-1} ${w+2} ${h+2}`} aria-label={`Prototype ${id}`}><polygon points={pts.map((p) => p.join(',')).join(' ')} fill={moduleColor(id)} stroke="#626262" strokeWidth=".18"/></svg>;
}
export function ModulePalette() {
  const s = useStore();
  const inventory = moduleInventory(s.graphState?.nodes, s.dictionary);
  const selected = (s.graphState?.nodes || []).find((n) => n.id === s.selectedOccurrenceId);
  return <aside className="module-sidebar">
    <div className="panel-heading"><div><span className="eyebrow">Library</span><h2>Module palette</h2></div><span className="count-tag">{inventory.length}</span></div>
    <p className="panel-caption">Select a prototype to highlight its occurrences. Function is listed separately.</p>
    <div className="module-list">
      {inventory.length === 0 && <div className="empty-palette">Your building’s reusable types appear here as it grows.<span>Train a policy or generate a layout to begin.</span></div>}
      {inventory.map((m) => <button key={m.id} className={`module-card ${s.selectedModuleId === m.id ? 'selected' : ''}`} onClick={() => s.setSelectedModuleId(m.id)} onMouseEnter={() => s.setHoveredModuleId(m.id)} onMouseLeave={() => s.setHoveredModuleId(null)} aria-pressed={s.selectedModuleId === m.id}>
        <span className="module-preview"><Shape shape={s.graphState?.realized ? m.shape : null} id={m.id}/></span>
        <span className="module-info"><strong><i style={{ background: moduleColor(m.id) }}/>{m.id}</strong><small>{[...m.functions].join(' · ')}</small><span title={`${format(m.independent)} independent occurrences · ${format(m.copies)} vertical floor copies`}>{format(m.independent)} uses <b>·</b> {format(m.copies)} copies</span></span>
      </button>)}
    </div>
    <div className="palette-note">{s.graphState?.realized ? 'Shapes shown from geometry preview.' : 'Constraint metadata · shapes available after preview.'}</div>
    <section className="occurrence-inspector"><span className="eyebrow">Occurrence details</span>{selected ? <><h3>{selected.id}</h3><dl><dt>Prototype</dt><dd>{selected.moduleId}</dd><dt>Function</dt><dd>{selected.type}</dd><dt>Occurrence</dt><dd>{selected.occurrenceId ?? 'Unavailable'}</dd><dt>Scope</dt><dd>{selected.scope ?? 'Unavailable'}</dd><dt>Floor</dt><dd>{selected.floor + 1}</dd><dt>Rotation</dt><dd>{selected.orientation == null ? '—' : `${format(selected.orientation * 180 / Math.PI, 1)}°`}</dd></dl></> : <p>Select a node or a room in the plan to inspect its identity and floor reference.</p>}</section>
  </aside>;
}

export function ConfigurationDrawer() {
  useDialogFocus();
  const s = useStore();
  const [draft, setDraft] = useState({ ...s.settings });
  const [browse, setBrowse] = useState({ ...s.filters });
  useEffect(() => { setDraft({ ...s.settings }); }, [s.settings]);
  const edit = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
  const graph = draft.generatorEngine === 'graph_voronoi';
  const changed = Object.keys(draft).some((k) => draft[k] !== s.settings[k]);
  const select = (label, key, options) => <label className="config-field">{label}<select value={['graphSpatialEnabled','graphPlotDirections'].includes(key) ? String(draft[key] ?? true) : (draft[key] ?? '')} onChange={(e) => edit(key, ['graphSpatialEnabled','graphPlotDirections'].includes(key) ? e.target.value === 'true' : e.target.value)}>{options.map(([v, l]) => <option key={String(v)} value={String(v)}>{l}</option>)}</select></label>;
  const input = (label, key, min, max, step = 1) => <label className="config-field">{label}<input type="number" value={draft[key] ?? ''} min={min} max={max} step={step} onChange={(e) => edit(key, e.target.value === '' ? '' : Number(e.target.value))}/></label>;
  return <div className="drawer-scrim" onClick={() => s.setActiveBottomDrawer(null)}><section className="workspace-drawer" role="dialog" aria-modal="true" aria-label="Configuration" onClick={(e) => e.stopPropagation()}>
    <div className="drawer-heading"><div><span className="eyebrow">Preferences</span><h2>Configuration</h2></div><button aria-label="Close configuration" onClick={() => s.setActiveBottomDrawer(null)}><X size={18}/></button></div>
    <p>Apply changes together. The optimizer returns the authoritative settings and a fresh site.</p>
    <div className="config-grid">
      {select('Generator engine', 'generatorEngine', [['graph_voronoi','Shared graph / Voronoi'],['discrete_polygon','Legacy discrete polygon']])}
      {select('Site boundary', 'boundaryType', [['free','Mixed procedural'],['real','Urban OSM plot'],['mixed','Procedural + OSM'],['rect','Rectangular'],['convex','Convex'],['lobed','Lobed'],['lshape','L-shaped'],['ushape','U-shaped'],['tshape','T-shaped']])}
      {select('Site area tier', 'siteAreaTier', ['ANY','XS','S','M','L','XL'].map((v) => [v,v]))}
      {input('Floors sharing a dictionary', 'parallelEnvironments', 1, 12)}
      {input('Maximum modules / floor', 'maxModules', 10, 300)}
      {input('Module type soft target', 'dictCap', 1, graph ? 15 : 30)}
      {graph && input('Module type hard ceiling', 'graphMaxTypes', 1, 15)}
      {input('Change site every N episodes (21 = never)', 'autoChangeEpisodes', 1, 21)}
    </div>
    <details className="advanced-settings"><summary><SlidersHorizontal size={14}/>Policy & advanced settings</summary><div className="config-grid">
      {graph && select('Controller', 'graphController', [['neural','Neural · experimental actor–critic'],['reference','Reference search']])}
      {graph && draft.graphController !== 'reference' && select('Proposal route', 'graphProposalStrategy', [['legacy','Current proposals'],['continuous','Continuous · experimental'],['vocabulary','Observed vocabulary + exploration · experimental']])}
      {graph && draft.graphController !== 'reference' && select('Policy architecture', 'graphPolicyArchitecture', [['message_passing','Message passing'],['pooled','Pooled'],['local_message_passing','Local message passing'],['candidate_attention','Candidate attention']])}
      {graph && draft.graphController === 'reference' && select('Search', 'graphSearchMode', [['balanced','Balanced'],['alternatives','Explore alternatives']])}
      {input('Learning rate', 'learningRate', .00001, .01, .0001)}
      {graph && select('Spatial proxy constraints', 'graphSpatialEnabled', [[true,'Enabled'],[false,'Disabled / baseline']])}
      {graph && input('Narrow crevice width threshold (m)', 'graphFacadeClearance', .1, 30, .5)}
      {graph && input('Daylight depth assumption (m)', 'graphDaylightDepth', 1, 20, .5)}
      {graph && input('Minimum vertical sky share', 'graphMinSkyShare', .01, 1, .05)}
      {graph && input('Window frontage per reference area (m)', 'graphWindowFrontage', .1, 10, .1)}
      {graph && input('Window reference area (m²)', 'graphWindowReferenceArea', 1, 100)}
      {graph && input('Facing window separation (m)', 'graphWindowSeparation', 1, 30)}
      {graph && input('Window cone, full angle (°)', 'graphWindowCone', 1, 179)}
      {graph && input('Allowed narrow-facing facade fraction', 'graphMaxCreviceFraction', .01, 1, .01)}
      {graph && select('Measured plot directions', 'graphPlotDirections', [[true,'Policy inputs + optional proposals'],[false,'Disabled / control']])}
      {graph && input('Minimum site fill for spatial feasibility', 'graphMinFill', .01, 1, .05)}
      {graph && input('Minimum residential share', 'graphMinResidentialShare', .01, 1, .05)}
      {graph && input('Maximum estimated core access (m)', 'graphMaxAccessDistance', 1, 120)}
      {graph && input('Livable area served per core (m²)', 'graphCoreCapacity', 50, 5000, 50)}
      {graph && input('Minimum core area assumption (m²)', 'graphMinCoreArea', 1, 80)}
      {graph && input('Minimum core width assumption (m)', 'graphMinCoreWidth', .5, 9, .5)}
      {!graph && input('Maximum room hops', 'maxRoomHops', 1, 10)}
      {!graph && input('Core shaft spacing (m)', 'coreSpacing', 4, 16)}
    </div><p>{graph ? 'Continuous angles are unsnapped. Spatial thresholds are experimental design assumptions, not standards. Livable rooms need at least the configured glazed-edge frontage, scaling above the reference area. Cores need no windows. Blank walls are excluded from privacy checks but count toward crevice quality. Footprint reuse does not certify identical opening fit-outs. Illuminance and sunlight remain unmeasured.' : 'Legacy geometry uses its own angle, clearance and daylight heuristics.'}</p></details>
    <section className="site-tools"><h3>Urban context</h3><p>Browse the existing site collection or open the custom-site map.</p><div className="config-grid"><label className="config-field">Browse city<select value={browse.city} onChange={(e) => setBrowse({ ...browse, city: e.target.value })}><option value="ALL">All cities</option>{[...new Set(s.allSites.map((site) => site.city_code))].sort().map((v) => <option key={v} value={v}>{v}</option>)}</select></label>{[['Minimum plot area (m²)','minArea',150,10000],['Maximum plot area (m²)','maxArea',150,10000],['Minimum context height (m)','minHeight',0,300],['Maximum context height (m)','maxHeight',0,300]].map(([label,key,min,max]) => <label key={key} className="config-field">{label}<input type="number" min={min} max={max} value={browse[key]} onChange={(e) => setBrowse({ ...browse, [key]: Number(e.target.value), activeTier: null })}/></label>)}</div><div className="browse-actions"><button disabled={s.pendingSite || browse.minArea > browse.maxArea || browse.minHeight > browse.maxHeight} onClick={() => { useStore.setState({ filters: browse }); s.applyFilters(); }}>Apply context filters</button><button onClick={s.resetFilters}>Reset filters</button><button onClick={() => { s.setActiveBottomDrawer(null); s.setCustomModalOpen(true); }}>Custom site map <ArrowRight size={14}/></button></div></section>
    <footer className="drawer-footer"><span>{changed ? 'Unapplied changes' : 'Settings up to date'}</span><button className="primary-action" disabled={!changed || !s.connected || s.pendingSite} onClick={() => { const patch = Object.fromEntries(Object.entries(draft).filter(([k,v]) => v !== s.settings[k])); s.updateSettings(patch); }}>Apply settings</button></footer>
  </section></div>;
}
