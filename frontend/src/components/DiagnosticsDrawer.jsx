import React from 'react';
import { X } from 'lucide-react';
import { useDialogFocus } from './useDialogFocus';
import { useStore } from '../store/useStore';
import { format, validationLabel, spatialFailureRows } from '../store/presentation';
export function DiagnosticsDrawer({onClose}) {
  useDialogFocus();
  const s=useStore(),m=s.metrics,d=s.diagnostics;
  const failures=spatialFailureRows(m,s.validation);
  const rows=[['Livable facade access proxy',m.daylightAccessProxy],['Spatial deficit',m.spatialDeficit],['Independent core occurrences',m.coreOccurrences],['Livable area evaluated (m²)',m.livableAreaEvaluated],['Policy updates',m.policyUpdateCount],['Gradient norm',m.gradientNorm],['Actor loss',m.actorLoss],['Value loss',m.valueLoss],['Independent occurrences',m.reuseAudit?.independentOccurrences],['Vertical copies',m.reuseAudit?.verticalCopies],['Experimental composite score',m.score],['Active client time, pauses excluded (ms)',d.clientWallTimeMs],['Server episode runtime (ms)',m.episodeExecutionTimeMs??d.episodeTimeMs],['Geometry validation time (ms)',m.postStepEvaluationMs??d.postStepEvaluationMs],['Last batch time (ms)',d.stepTimeMs],['Observed edge lengths',s.graphState?.proposalVocabulary?.observedLengthCount],['Observed relative angles',s.graphState?.proposalVocabulary?.observedAngleCount]];
  return <div className="drawer-scrim" onClick={onClose}><section className="workspace-drawer" role="dialog" aria-modal="true" aria-label="Diagnostics" onClick={(e)=>e.stopPropagation()}><div className="drawer-heading"><div><span className="eyebrow">LEARNING & VALIDATION</span><h2>Diagnostics</h2></div><button aria-label="Close diagnostics" onClick={onClose}><X size={18}/></button></div>
    <p>Losses and gradient updates establish that training runs. They do not establish useful learning or architectural quality.</p>
    <section className="diagnostic-section"><h3>{validationLabel(s.validation)}</h3><p>Shared definitions: {m.moduleIdentityStatus??'unavailable'}. Graph connectivity: {s.validation?.graphValid==null&&m.graphValid==null?'unmeasured':(s.validation?.graphValid??m.graphValid)?'passed':'failed'}.</p>{s.validation?.violations?.length>0&&<pre>{JSON.stringify(s.validation.violations,null,2)}</pre>}{s.validation?.unresolved?.length>0&&<pre>{JSON.stringify(s.validation.unresolved,null,2)}</pre>}</section>
    <dl className="diagnostic-values">{rows.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{format(value,3)}</dd></React.Fragment>)}</dl>
    <section className="diagnostic-section"><h3>Last completed decisions</h3><p>Source counts refer to the most recently completed episode, not the current partial layout.</p><pre>{JSON.stringify(m.selectedProposalSources||{},null,2)}</pre><pre>{JSON.stringify(m.selectedFactorSources||{},null,2)}</pre></section>
    <section className="diagnostic-section"><h3>Prediction differences</h3><pre>{s.predictionErrors?JSON.stringify(s.predictionErrors,null,2):'No geometry comparison available.'}</pre></section>
    <section className="diagnostic-section"><h3>Livable exposure requirements</h3><ul>{failures.map((row)=><li key={row.floor}>Floor {row.floor}: {row.failed.join(', ')}</li>)}</ul><p>Only livable rooms require daylight access. Cores are exempt and can obstruct rooms. Facade access is a proxy; illuminance, windows, climate and external context shading are unmeasured.</p><pre>{JSON.stringify(m.spatialPerFloor || [],null,2)}</pre><p>Access distances follow the room graph; private/public circulation and regulatory egress are not established.</p></section>
  </section></div>;
}
