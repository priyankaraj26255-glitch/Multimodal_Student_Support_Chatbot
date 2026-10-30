import { memo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Check, Copy, FileText, Loader2, Pause, RefreshCw, Sparkles, Volume2 } from 'lucide-react';
import AuthedImage from './AuthedImage.jsx';

const textOf = (n) => (typeof n === 'string' ? n : Array.isArray(n) ? n.map(textOf).join('') : n?.props?.children ? textOf(n.props.children) : '');

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  const lang = children?.props?.className?.match(/language-([\w-]+)/)?.[1];
  const copy = async () => {
    try { await navigator.clipboard.writeText(textOf(children).replace(/\n$/, '')); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ }
  };
  return (
    <div className="not-prose my-3 overflow-hidden rounded-xl border border-slate-700/40 bg-slate-900 text-slate-100">
      <div className="flex items-center justify-between bg-slate-800 px-3 py-1.5 text-xs text-slate-300">
        <span>{lang || 'code'}</span>
        <button onClick={copy} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-slate-700" aria-label="Copy code">{copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : 'Copy'}</button>
      </div>
      <pre className="scroll-thin overflow-x-auto p-4 text-[13px] leading-relaxed">{children}</pre>
    </div>
  );
}

const components = {
  a: ({ node, ...p }) => <a {...p} target="_blank" rel="noopener noreferrer nofollow" />,
  pre: CodeBlock,
  table: ({ node, ...p }) => <div className="scroll-thin overflow-x-auto"><table {...p} /></div>,
};

export function Markdown({ children }) {
  return (
    <div className="prose prose-slate max-w-none break-words text-[15px] dark:prose-invert prose-p:leading-7 prose-pre:m-0 prose-pre:bg-transparent prose-pre:p-0 prose-code:before:hidden prose-code:after:hidden prose-th:bg-slate-50 dark:prose-th:bg-slate-800">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]} components={components}>{children}</ReactMarkdown>
    </div>
  );
}

function Attachments({ files }) {
  if (!files?.length) return null;
  return (
    <div className="mb-2 flex flex-wrap justify-end gap-2">
      {files.map((f) => f.kind === 'image'
        ? <AuthedImage key={f.id} id={f.id} alt={f.filename} className="h-28 w-28 rounded-xl object-cover shadow" />
        : <div key={f.id} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"><FileText size={16} className="text-brand-600" /><span className="max-w-[10rem] truncate">{f.filename}</span>{f.page_count ? <span className="text-slate-400">{f.page_count}p</span> : null}</div>)}
    </div>
  );
}

function Message({ m, isLast, busy, speaking, onCopy, onRegenerate, onSpeak, onStopSpeak }) {
  const [copied, setCopied] = useState(false);
  if (m.role === 'user') {
    return (
      <div className="flex flex-col items-end">
        <Attachments files={m.attachments} />
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[15px] leading-7 text-white shadow-sm sm:max-w-[75%]">{m.content}</div>
      </div>
    );
  }
  const copy = () => { onCopy(m.content); setCopied(true); setTimeout(() => setCopied(false), 1500); };
  const showActions = !m.streaming && m.content;
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-violet-500 text-white"><Sparkles size={15} /></div>
      <div className="min-w-0 flex-1">
        {m.content ? <Markdown>{m.content}</Markdown> : null}
        {m.streaming && !m.content && (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500" role="status">
            <span className="flex gap-1">{[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${i * 0.15}s` }} />)}</span>
            {m.status || 'Thinking…'}
          </div>
        )}
        {m.streaming && m.content && <span className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-brand-500 align-middle" />}
        {m.error && (
          <div role="alert" className="mt-2 flex flex-wrap items-center gap-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            <span className="min-w-0 flex-1">{m.error}</span>
            {isLast && !busy && <button onClick={onRegenerate} className="inline-flex items-center gap-1 rounded-md border border-red-300 px-2 py-1 text-xs font-medium hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-900"><RefreshCw size={12} /> Try again</button>}
          </div>
        )}
        {m.sources?.length > 0 && !m.streaming && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500">Sources:</span>
            {m.sources.map((s, i) => (
              <span key={i} title={s.snippet || s.filename} className="inline-flex max-w-[16rem] items-center gap-1 truncate rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"><FileText size={11} className="shrink-0" /><span className="truncate">{s.label}</span></span>
            ))}
          </div>
        )}
        {showActions && (
          <div className="-ml-2 mt-1 flex items-center gap-0.5">
            <button className="btn-icon h-8 w-8" onClick={copy} aria-label="Copy response" title="Copy">{copied ? <Check size={15} /> : <Copy size={15} />}</button>
            <button className="btn-icon h-8 w-8" onClick={() => (speaking === 'playing' || speaking === 'paused' ? onStopSpeak() : onSpeak(m))} aria-label={speaking ? 'Stop reading aloud' : 'Read aloud'} title={speaking ? 'Stop' : 'Read aloud'}>
              {speaking === 'loading' ? <Loader2 size={15} className="animate-spin" /> : speaking ? <Pause size={15} /> : <Volume2 size={15} />}
            </button>
            {isLast && <button className="btn-icon h-8 w-8" onClick={onRegenerate} disabled={busy} aria-label="Regenerate response" title="Regenerate"><RefreshCw size={15} /></button>}
          </div>
        )}
      </div>
    </div>
  );
}

export default memo(Message);
