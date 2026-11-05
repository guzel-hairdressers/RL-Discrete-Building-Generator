import React from 'react';
import { X } from 'lucide-react';
import { useDialogFocus } from './useDialogFocus';
import { useStore } from '../store/useStore';
import { format, validationLabel } from '../store/presentation';
export function DiagnosticsDrawer({onClose}) {
  useDialogFocus();
  const s=useStore(),m=s.metrics,d=s.diagnostics;
  const rows=[['Policy updates',m.policyUpdateCount],['Gradient norm',m.gradientNorm],['Actor loss',m.actorLoss],['Value loss',m.valueLoss],['Independent occurrences',m.reuseAudit?.independentOccurrences],['Vertical copies',m.reuseAudit?.verticalCopies],['Experimental composite score',m.score],['Client episode wall time (ms)',d.clientWallTimeMs],['Server episode runtime (ms)',m.episodeExecutionTimeMs??d.episodeTimeMs],['Geometry validation time (ms)',m.postStepEvaluationMs??d.postStepEvaluationMs],['Last batch time (ms)',d.stepTimeMs],['Observed edge lengths',s.graphState?.proposalVocabulary?.observedLengthCount],['Observed relative angles',s.graphState?.proposalVocabulary?.observedAngleCount]];
  return <div className="drawer-scrim" onClick={onClose}><section className="workspace-drawer" role="dialog" aria-modal="true" aria-label="Diagnostics" onClick={(e)=>e.stopPropagation()}><div className="drawer-heading"><div><span className="eyebrow">LEARNING & VALIDATION</span><h2>Diagnostics</h2></div><button aria-label="Close diagnostics" onClick={onClose}><X size={18}/></button></div>
    <p>Losses and gradient updates establish that training runs. They do not establish useful learning or architectural quality.</p>
    <section className="diagnostic-section"><h3>{validationLabel(s.validation)}</h3><p>Shared definitions: {m.moduleIdentityStatus??'unavailable'}. Graph connectivity: {s.validation?.graphValid==null&&m.graphValid==null?'unmeasured':(s.validation?.graphValid??m.graphValid)?'passed':'failed'}.</p>{s.validation?.violations?.length>0&&<pre>{JSON.stringify(s.validation.violations,null,2)}</pre>}{s.validation?.unresolved?.length>0&&<pre>{JSON.stringify(s.validation.unresolved,null,2)}</pre>}</section>
    <dl className="diagnostic-values">{rows.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{format(value,3)}</dd></React.Fragment>)}</dl>
    <section className="diagnostic-section"><h3>Last completed decisions</h3><p>Source counts refer to the most recently completed episode, not the current partial layout.</p><pre>{JSON.stringify(m.selectedProposalSources||{},null,2)}</pre><pre>{JSON.stringify(m.selectedFactorSources||{},null,2)}</pre></section>
    <section className="diagnostic-section"><h3>Prediction differences</h3><pre>{s.predictionErrors?JSON.stringify(s.predictionErrors,null,2):'No geometry comparison available.'}</pre></section>
    <section className="diagnostic-section"><h3>Unmeasured</h3><p>Daylight, sunlight and environmental performance have not been evaluated. Geometry and access checks are separate from these metrics.</p></section>
  </section></div>;
}
