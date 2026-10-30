import { useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { api } from '../lib/api.js';

const VOICES = ['alloy', 'ash', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer'];

export default function SettingsModal({ prefs, caps, onSaved, onClose, onHistoryDeleted, onAccountDeleted, toast }) {
  const [p, setP] = useState(prefs);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const set = (k, v) => setP((x) => ({ ...x, [k]: v }));

  const save = async () => {
    setBusy(true);
    try { onSaved(await api.savePreferences(p)); toast('Settings saved.', 'success'); onClose(); }
    catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
  };
  const danger = async (kind) => {
    setBusy(true);
    try {
      if (kind === 'history') { await api.deleteHistory(); onHistoryDeleted(); toast('All conversations and uploaded files were deleted.', 'success'); onClose(); }
      else { await api.deleteAccount(); onAccountDeleted(); }
    } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); setConfirm(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Settings" onClick={onClose}>
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-2xl dark:bg-slate-900" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800"><h2 className="font-semibold">Settings</h2><button className="btn-icon" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        <div className="scroll-thin flex-1 space-y-6 overflow-y-auto p-5 text-sm">
          <section className="space-y-3">
            <h3 className="font-medium">Language & voice</h3>
            <label className="block"><span className="mb-1 block text-xs text-slate-500">Default response language</span>
              <select className="input" value={p.language} onChange={(e) => set('language', e.target.value)}>
                <option value="auto">Auto-detect (reply in the language I write)</option><option value="en">English</option><option value="hi">हिन्दी (Hindi)</option><option value="mr">मराठी (Marathi)</option>
              </select></label>
            <label className="block"><span className="mb-1 block text-xs text-slate-500">Voice for read-aloud</span>
              <select className="input" value={p.tts_voice} onChange={(e) => set('tts_voice', e.target.value)}>{VOICES.map((v) => <option key={v}>{v}</option>)}</select></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={p.auto_speak} onChange={(e) => set('auto_speak', e.target.checked)} /> Read replies aloud automatically</label>
          </section>
          <section className="space-y-3">
            <h3 className="font-medium">Personalization <span className="text-xs font-normal text-slate-500">(optional)</span></h3>
            <label className="flex items-center gap-2"><input type="checkbox" checked={p.personalization_enabled} onChange={(e) => set('personalization_enabled', e.target.checked)} /> Let the assistant use background I provide</label>
            {p.personalization_enabled && <textarea className="input" rows={3} maxLength={2000} placeholder="e.g. I’m a CS student preparing for interviews; I prefer short code examples." value={p.about_me} onChange={(e) => set('about_me', e.target.value)} aria-label="About me" />}
            <p className="text-xs text-slate-500">Off by default. Turning it off deletes the saved text.</p>
          </section>
          <section className="space-y-3">
            <h3 className="font-medium">Privacy & data</h3>
            <p className="text-xs text-slate-500">Uploaded files are {caps?.file_retention_days ? `deleted automatically after ${caps.file_retention_days} days` : 'kept until you delete them'}. You can delete everything at any time.</p>
            {confirm ? (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950">
                <p className="mb-2 text-sm text-red-800 dark:text-red-200">{confirm === 'history' ? 'Permanently delete ALL conversations, messages, files and embeddings?' : 'Permanently delete your account and ALL data?'} This cannot be undone.</p>
                <div className="flex gap-2"><button className="btn-danger !py-1.5" onClick={() => danger(confirm)} disabled={busy}>{busy && <Loader2 size={14} className="animate-spin" />} Yes, delete</button><button className="btn-ghost !py-1.5" onClick={() => setConfirm(null)}>Cancel</button></div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2"><button className="btn-danger" onClick={() => setConfirm('history')}>Delete all chats & files</button><button className="btn-danger" onClick={() => setConfirm('account')}>Delete account</button></div>
            )}
          </section>
          {caps && (
            <section className="space-y-1 text-xs text-slate-500">
              <h3 className="text-sm font-medium text-slate-900 dark:text-slate-100">Server status</h3>
              <p>AI provider: {caps.ai_configured ? `configured (${caps.chat_model})` : 'NOT configured – set GEMINI_API_KEY'}</p>
              <p>OCR: {caps.ocr_tesseract ? `Tesseract (${caps.ocr_languages.join(', ')})` : 'Tesseract not installed – AI vision OCR only'}</p>
            </section>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800"><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy}>Save</button></div>
      </div>
    </div>
  );
}
