import { useEffect, useRef, useState } from 'react';
import { ArrowUp, FileText, Image as ImageIcon, Loader2, Mic, Paperclip, ScanText, Square, X } from 'lucide-react';
import { api, uid } from '../lib/api.js';
import { useRecorder, voiceSupported } from '../hooks/useRecorder.js';

const IMG_ACCEPT = 'image/png,image/jpeg,image/webp,image/gif,image/bmp';
const DOC_ACCEPT = '.pdf,.docx,.txt,.md,.csv,application/pdf';
const QUICK = [['Summarize', 'Summarize this document with key points and page references.'], ['Quiz', 'Create a quiz of 8 multiple-choice questions from this document, with an answer key.'], ['Flashcards', 'Create flashcards from this document.'], ['Study notes', 'Write organised study notes from this document.']];

export default function Composer({ onSend, onStop, streaming, caps, toast, hasDocs, language, onReview }) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [transcribing, setTranscribing] = useState(false);
  const [drag, setDrag] = useState(false);
  const ta = useRef(null);
  const imgIn = useRef(null);
  const docIn = useRef(null);
  const ctrls = useRef({});
  const fromVoice = useRef(false);
  const rec = useRecorder();

  useEffect(() => {
    if (!ta.current) return;
    ta.current.style.height = 'auto';
    ta.current.style.height = Math.min(ta.current.scrollHeight, 200) + 'px';
  }, [text]);

  const patch = (id, p) => setFiles((fs) => fs.map((f) => (f.id === id ? { ...f, ...p } : f)));

  const addFiles = (list) => {
    for (const file of Array.from(list)) {
      const isImg = file.type.startsWith('image/');
      const max = (isImg ? caps?.max_image_mb : caps?.max_doc_mb) || 25;
      if (file.size > max * 1024 * 1024) { toast(`${file.name} is larger than ${max} MB.`, 'error'); continue; }
      const id = uid();
      const ctrl = new AbortController();
      ctrls.current[id] = ctrl;
      setFiles((fs) => [...fs, { id, name: file.name, isImg, progress: 0, status: 'uploading', preview: isImg ? URL.createObjectURL(file) : null }]);
      api.upload(file, (p) => patch(id, { progress: p }), ctrl.signal)
        .then((server) => patch(id, { status: 'ready', progress: 100, server }))
        .catch((e) => { if (e.name !== 'AbortError') { patch(id, { status: 'error', error: e.message }); toast(`${file.name}: ${e.message}`, 'error'); } });
    }
  };

  const remove = (f) => {
    ctrls.current[f.id]?.abort();
    if (f.server) api.deleteFile(f.server.id).catch(() => {});
    if (f.preview) URL.revokeObjectURL(f.preview);
    setFiles((fs) => fs.filter((x) => x.id !== f.id));
  };

  const ready = files.filter((f) => f.status === 'ready');
  const uploading = files.some((f) => f.status === 'uploading');
  const canSend = !streaming && !uploading && !transcribing && !rec.recording && (text.trim() || ready.length);

  const submit = (override) => {
    if (!canSend && !override) return;
    const attached = ready.map((f) => f.server);
    let content = (override || text).trim();
    if (!content) content = attached.some((f) => f.kind === 'document') ? 'Summarize this document.' : 'Describe this image and explain what it shows.';
    onSend({ text: content, files: attached, inputMode: fromVoice.current ? 'voice' : 'text' });
    files.forEach((f) => f.preview && setTimeout(() => URL.revokeObjectURL(f.preview), 60000));
    setText(''); setFiles([]); fromVoice.current = false;
  };

  const toggleMic = async () => {
    if (rec.recording) {
      const blob = await rec.stop();
      if (!blob) return toast('No audio was captured. Please try again.', 'error');
      setTranscribing(true);
      try {
        const r = await api.transcribe(blob, language);
        setText((t) => (t ? t + ' ' : '') + r.text);
        fromVoice.current = true;
        ta.current?.focus();
      } catch (e) { toast(e.message, 'error'); } finally { setTranscribing(false); }
    } else {
      const err = await rec.start();
      if (err) toast(err, 'error');
    }
  };

  const onPaste = (e) => {
    const imgs = Array.from(e.clipboardData?.files || []).filter((f) => f.type.startsWith('image/'));
    if (imgs.length) { e.preventDefault(); addFiles(imgs); }
  };
  const mmss = `${Math.floor(rec.seconds / 60)}:${String(rec.seconds % 60).padStart(2, '0')}`;
  const showQuick = !streaming && !text.trim() && (hasDocs || ready.some((f) => !f.isImg));

  return (
    <div className="mx-auto w-full max-w-3xl px-3 pb-3 pt-1 sm:px-4 sm:pb-4"
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); }}>
      {showQuick && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {QUICK.map(([label, prompt]) => <button key={label} onClick={() => submit(prompt)} className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 transition hover:border-brand-400 hover:bg-brand-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900">{label}</button>)}
        </div>
      )}
      <div className={`rounded-2xl border bg-white shadow-sm transition dark:bg-slate-900 ${drag ? 'border-brand-500 ring-2 ring-brand-500/30' : 'border-slate-300 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20 dark:border-slate-700'}`}>
        {files.length > 0 && (
          <ul className="flex flex-wrap gap-2 px-3 pt-3" aria-label="Attached files">
            {files.map((f) => (
              <li key={f.id} className="relative flex items-center gap-2 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 py-1.5 pl-1.5 pr-8 text-xs dark:border-slate-700 dark:bg-slate-800">
                {f.isImg && f.preview ? <img src={f.preview} alt="" className="h-9 w-9 rounded-lg object-cover" /> : <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-100 text-brand-600"><FileText size={16} /></span>}
                <div className="min-w-0">
                  <p className="max-w-[9rem] truncate font-medium">{f.name}</p>
                  <p className={f.status === 'error' ? 'text-red-600' : 'text-slate-500'}>
                    {f.status === 'uploading' ? (f.progress >= 100 ? 'Processing…' : `Uploading ${f.progress}%`) : f.status === 'error' ? 'Failed' : f.server?.page_count ? `${f.server.page_count} pages ready` : 'Ready'}
                  </p>
                </div>
                {f.status === 'ready' && <button className="rounded p-1 text-slate-400 hover:text-brand-600" onClick={() => onReview(f.server)} aria-label={`Review text of ${f.name}`} title="Review / extract text"><ScanText size={14} /></button>}
                <button className="absolute right-1 top-1 rounded p-1 text-slate-400 hover:text-red-600" onClick={() => remove(f)} aria-label={`Remove ${f.name}`}><X size={13} /></button>
                {f.status === 'uploading' && <span className="absolute bottom-0 left-0 h-0.5 bg-brand-500 transition-all" style={{ width: `${f.progress}%` }} />}
              </li>
            ))}
          </ul>
        )}
        {rec.recording && (
          <div className="mx-3 mt-3 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-700 dark:bg-red-950 dark:text-red-300" role="status">
            <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" /> Recording {mmss} — tap the microphone to stop and transcribe
          </div>
        )}
        {transcribing && <div className="mx-3 mt-3 flex items-center gap-2 text-xs text-slate-500" role="status"><Loader2 size={13} className="animate-spin" /> Transcribing your speech…</div>}
        <textarea ref={ta} rows={1} value={text} onChange={(e) => { setText(e.target.value); fromVoice.current = false; }} onPaste={onPaste}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
          placeholder={fromVoice.current ? 'Review the transcription, then press send…' : 'Message the assistant… (Shift+Enter for a new line)'} aria-label="Message"
          className="block max-h-[200px] w-full resize-none bg-transparent px-4 py-3 text-[15px] outline-none placeholder:text-slate-400" maxLength={20000} />
        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center">
            <button className="btn-icon" onClick={() => imgIn.current.click()} aria-label="Attach image" title="Attach image"><ImageIcon size={18} /></button>
            <button className="btn-icon" onClick={() => docIn.current.click()} aria-label="Attach PDF or document" title="Attach PDF / document"><Paperclip size={18} /></button>
            <button className={`btn-icon ${rec.recording ? '!bg-red-100 !text-red-600 dark:!bg-red-950' : ''}`} onClick={toggleMic} disabled={transcribing || (!voiceSupported() && false)}
              aria-label={rec.recording ? 'Stop recording' : 'Record voice message'} title={voiceSupported() ? (rec.recording ? 'Stop recording' : 'Voice input') : 'Voice input is not available in this browser'}>
              {rec.recording ? <Square size={16} /> : <Mic size={18} />}
            </button>
          </div>
          {streaming
            ? <button onClick={onStop} aria-label="Stop generating" title="Stop generating" className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700 dark:bg-white dark:text-slate-900"><Square size={14} fill="currentColor" /></button>
            : <button onClick={() => submit()} disabled={!canSend} aria-label="Send message" title="Send" className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"><ArrowUp size={18} /></button>}
        </div>
      </div>
      <input ref={imgIn} type="file" hidden multiple accept={IMG_ACCEPT} onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
      <input ref={docIn} type="file" hidden multiple accept={DOC_ACCEPT} onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
      <p className="mt-2 text-center text-[11px] text-slate-400">AI can make mistakes. Check important information against your sources.</p>
    </div>
  );
}
