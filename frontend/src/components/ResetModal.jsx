import React from 'react';
import { useStore } from '../store/useStore';
import { useDialogFocus } from './useDialogFocus';
function ResetConfirmation({ close, reset }) {
  useDialogFocus();
  return <div className="confirm-modal-overlay"><div className="confirm-modal-content glass-card" role="dialog" aria-modal="true" aria-labelledby="reset-policy-title">
    <h3 id="reset-policy-title">Reset policy weights?</h3>
    <p>This will erase all training progress and reset model weights to random initialization.</p>
    <div className="confirm-modal-buttons"><button className="confirm-btn cancel-btn" onClick={close}>Cancel</button><button className="confirm-btn reset-btn" onClick={reset}>Yes, Reset</button></div>
  </div></div>;
}
export function ResetModal() {
  const open=useStore((s)=>s.resetConfirmOpen), close=useStore((s)=>s.setResetConfirmOpen), reset=useStore((s)=>s.resetPolicy);
  return open ? <ResetConfirmation close={()=>close(false)} reset={reset}/> : null;
}
