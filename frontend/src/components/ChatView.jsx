import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, PanelLeft } from 'lucide-react';
import { api, streamSSE, uid } from '../lib/api.js';
import Composer from './Composer.jsx';
import EmptyState from './EmptyState.jsx';
import Message from './MessageBubble.jsx';

const LANGS = [['auto', 'Auto'], ['en', 'English'], ['hi', 'हिन्दी'], ['mr', 'मराठी']];

export default function ChatView({ convId, title, onCreated, onListChanged, prefs, caps, toast, player, user, onReview, onToggleSidebar }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [language, setLanguage] = useState(prefs.language);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const stick = useRef(true);
  const skipLoad = useRef(null);
  const idRef = useRef(convId);
  idRef.current = convId;

  useEffect(() => {
    if (skipLoad.current && skipLoad.current === convId) { skipLoad.current = null; return; }
    abortRef.current?.abort();
    if (!convId) { setMessages([]); setLanguage(prefs.language); return; }
    let alive = true;
    setLoading(true);
    api.getConversation(convId)
      .then((c) => { if (alive) { setMessages(c.messages); setLanguage(c.language); stick.current = true; } })
      .catch((e) => toast(e.message, 'error'))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [convId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (!convId) setLanguage(prefs.language); }, [prefs.language, convId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const updateLast = (patch) => setMessages((ms) => {
    if (!ms.length) return ms;
    const c = [...ms];
    const cur = c[c.length - 1];
    c[c.length - 1] = { ...cur, ...(typeof patch === 'function' ? patch(cur) : patch) };
    return c;
  });

  const run = async (id, path, body) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    let aborted = false, done = false, errorMsg = null, spoken = '';
    try {
      await streamSSE(path, body, (ev, d) => {
        if (ev === 'meta') {
          const r = d.route || {};
          updateLast({ status: r.mode ? `Preparing your ${r.mode}…` : r.intents?.includes('document') ? 'Searching your documents…' : r.intents?.includes('image') ? 'Looking at your image…' : 'Thinking…' });
        } else if (ev === 'token') { spoken += d.text; updateLast((m) => ({ content: m.content + d.text })); }
        else if (ev === 'tool') updateLast({ status: d.name === 'ocr_image' ? 'Reading text from the image…' : 'Searching documents…' });
        else if (ev === 'done') { done = true; updateLast({ streaming: false, sources: d.sources }); }
        else if (ev === 'error') { errorMsg = d.message; updateLast({ streaming: false, error: d.message }); }
      }, ctrl.signal);
    } catch (e) {
      if (e.name === 'AbortError') aborted = true;
      else { errorMsg = e.message; updateLast({ streaming: false, error: e.message }); toast(e.message, 'error'); }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
    if (idRef.current !== id) return; // user navigated away
    if (aborted) await new Promise((r) => setTimeout(r, 400)); // let the server persist the partial reply
    try {
      const c = await api.getConversation(id);
      if (idRef.current === id) setMessages(errorMsg ? [...c.messages, { id: 'err' + uid(), role: 'assistant', content: '', error: errorMsg }] : c.messages);
      onListChanged();
    } catch { /* keep optimistic UI */ }
    if (done && prefs.auto_speak && spoken) player.play(spoken, 'auto');
  };

  const send = async ({ text, files, inputMode }) => {
    let id = convId;
    if (!id) {
      try {
        const c = await api.createConversation({ language });
        id = c.id;
        skipLoad.current = id;
        onCreated(c);
      } catch (e) { toast(e.message, 'error'); return; }
    }
    stick.current = true;
    setMessages((ms) => [...ms,
      { id: 'u' + uid(), role: 'user', content: text, attachments: files, created_at: new Date().toISOString() },
      { id: 'a' + uid(), role: 'assistant', content: '', streaming: true, status: 'Thinking…' }]);
    await run(id, `/conversations/${id}/messages`, { content: text, attachment_ids: files.map((f) => f.id), language, input_mode: inputMode });
  };

  const regenerate = async () => {
    if (!convId || streaming) return;
    setMessages((ms) => {
      const c = ms[ms.length - 1]?.role === 'assistant' ? ms.slice(0, -1) : ms;
      return [...c, { id: 'a' + uid(), role: 'assistant', content: '', streaming: true, status: 'Thinking…' }];
    });
    stick.current = true;
    await run(convId, `/conversations/${convId}/regenerate`);
  };

  const changeLanguage = (v) => {
    setLanguage(v);
    if (convId) api.updateConversation(convId, { language: v }).catch((e) => toast(e.message, 'error'));
  };

  const copy = useCallback(async (t) => { try { await navigator.clipboard.writeText(t); } catch { toast('Could not copy to the clipboard.', 'error'); } }, [toast]);
  const hasDocs = messages.some((m) => m.attachments?.some((a) => a.kind === 'document'));

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <header className="flex items-center gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <button className="btn-icon" onClick={onToggleSidebar} aria-label="Toggle sidebar" title="Toggle sidebar"><PanelLeft size={18} /></button>
        <h1 className="min-w-0 flex-1 truncate text-sm font-medium">{title || 'New chat'}</h1>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <span className="hidden sm:inline">Reply in</span>
          <select value={language} onChange={(e) => changeLanguage(e.target.value)} aria-label="Response language" className="rounded-lg border border-slate-300 bg-transparent px-2 py-1.5 text-xs text-slate-800 dark:border-slate-700 dark:text-slate-100 dark:[&>option]:bg-slate-900">
            {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
      </header>

      {caps && !caps.ai_configured && (
        <div role="alert" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          The server has no AI API key configured. Set <code>GEMINI_API_KEY</code> in <code>.env</code> and restart the backend to enable answers.
        </div>
      )}

      <div ref={scrollRef} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}
        role="log" aria-live={streaming ? 'off' : 'polite'} aria-label="Conversation" className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        {loading ? <div className="flex h-full items-center justify-center"><Loader2 className="animate-spin text-slate-400" /></div>
          : messages.length === 0 ? <EmptyState name={user.display_name?.split(' ')[0]} onPick={(t) => send({ text: t, files: [], inputMode: 'text' })} />
          : (
            <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
              {messages.map((m, i) => (
                <Message key={m.id} m={m} isLast={i === messages.length - 1} busy={streaming}
                  speaking={player.state.id === m.id ? player.state.status : null}
                  onCopy={copy} onRegenerate={regenerate} onSpeak={(msg) => player.play(msg.content, msg.id)} onStopSpeak={player.stop} />
              ))}
            </div>
          )}
      </div>
      <Composer onSend={send} onStop={() => abortRef.current?.abort()} streaming={streaming} caps={caps} toast={toast} hasDocs={hasDocs} language={language} onReview={onReview} />
    </div>
  );
}
