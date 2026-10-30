import { BookOpen, FileText, Image, Languages, Mic, Sparkles } from 'lucide-react';

const PROMPTS = [
  { icon: Sparkles, title: 'Explain a concept', text: 'Explain how neural networks learn, with a simple analogy and a small Python example.' },
  { icon: FileText, title: 'Chat with a PDF', text: 'Upload a PDF, then ask: “Summarize this document and list the 5 key takeaways with page numbers.”', attach: true },
  { icon: Image, title: 'Analyze an image', text: 'Upload a chart or screenshot and ask: “What does this show? Explain the key insights.”', attach: true },
  { icon: BookOpen, title: 'Study helper', text: 'Create a quiz of 8 multiple-choice questions on the French Revolution with an answer key.' },
  { icon: Languages, title: 'हिन्दी / मराठी', text: 'प्रकाशसंश्लेषण म्हणजे काय ते सोप्या मराठीत समजावून सांगा.' },
  { icon: Mic, title: 'Use your voice', text: 'Tap the microphone, ask a question out loud, review the transcript and send it.', attach: true },
];

export default function EmptyState({ onPick, name }) {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-4 py-10 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-lg"><Sparkles size={28} /></div>
      <h2 className="text-2xl font-semibold tracking-tight">{name ? `Hi ${name}, how can I help?` : 'How can I help you today?'}</h2>
      <p className="mt-2 max-w-md text-sm text-slate-500 dark:text-slate-400">Ask anything, or attach images, PDFs and documents. I’ll cite the pages I use and tell you when something isn’t in your files.</p>
      <div className="mt-8 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {PROMPTS.map(({ icon: Icon, title, text, attach }) => (
          <button key={title} disabled={attach} onClick={() => onPick(text)} title={attach ? 'Tip – use the attach / mic buttons below' : undefined}
            className="group flex items-start gap-3 rounded-xl border border-slate-200 p-3.5 text-left transition enabled:hover:border-brand-400 enabled:hover:bg-brand-50/60 disabled:cursor-default dark:border-slate-800 dark:enabled:hover:bg-slate-900">
            <Icon size={18} className="mt-0.5 shrink-0 text-brand-600 dark:text-brand-400" />
            <span><span className="block text-sm font-medium">{title}</span><span className="mt-0.5 line-clamp-2 block text-xs text-slate-500 dark:text-slate-400">{text}</span></span>
          </button>
        ))}
      </div>
    </div>
  );
}
