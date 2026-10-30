import { useEffect, useState } from 'react';
import { Loader2, ScanText, X } from 'lucide-react';
import { api } from '../lib/api.js';

/** Review extracted text. Images: run OCR (auto/Tesseract/AI vision), edit and save. Documents: read-only. */
export default function TextModal({ file, onClose, toast }) {
  const [text, setText] = useState('');
  const [editable, setEditable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [engine, setEngine] = useState('auto');
  const [info, setInfo] = useState(null);

  useEffect(() => {
    api.fileText(file.id).then((r) => { setText(r.text); setEditable(r.editable); }).catch((e) => toast(e.message, 'error')).finally(() => setLoading(false));
  }, [file.id]); // eslint-disable-line

  const runOcr = async () => {
    setBusy(true); setInfo(null);
    try {
      const r = await api.runOcr(file.id, engine);
      setText(r.text); setInfo(r);
    } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true);
    try { await api.saveFileText(file.id, text); toast('Text saved. It will be used when you ask about this image.', 'success'); onClose(); }
    catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Extracted text" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl dark:bg-slate-900" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h2 className="truncate font-semibold">{editable ? 'Extract & review text' : 'Extracted text'} — <span className="font-normal text-slate-500">{file.filename}</span></h2>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {editable && (
            <div className="flex flex-wrap items-center gap-2">
              <select value={engine} onChange={(e) => setEngine(e.target.value)} className="input !w-auto !py-2" aria-label="OCR engine">
                <option value="auto">Auto (Tesseract → AI vision)</option>
                <option value="tesseract">Tesseract (printed text)</option>
                <option value="vision">AI vision (handwriting / low quality)</option>
              </select>
              <button className="btn-ghost !py-2" onClick={runOcr} disabled={busy}>{busy ? <Loader2 size={15} className="animate-spin" /> : <ScanText size={15} />} Run OCR</button>
            </div>
          )}
          {info?.warnings?.map((w, i) => <p key={i} className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">{w}</p>)}
          {info && <p className="text-xs text-slate-500">Engine: {info.engine}{info.confidence != null ? ` · confidence ${Math.round(info.confidence)}%` : ''}</p>}
          {loading ? <Loader2 className="mx-auto animate-spin" /> : (
            <textarea value={text} onChange={(e) => setText(e.target.value)} readOnly={!editable} rows={14} aria-label="Extracted text"
              placeholder={editable ? 'No text yet. Click “Run OCR”, or type/paste the text yourself.' : 'No text available.'} className="input scroll-thin font-mono !text-[13px]" />
          )}
        </div>
        {editable && <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800"><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy}>Save text</button></div>}
      </div>
    </div>
  );
}
