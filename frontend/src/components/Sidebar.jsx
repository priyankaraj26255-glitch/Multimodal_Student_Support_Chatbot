import { useEffect, useRef, useState } from 'react';
import { Check, LogOut, Monitor, Moon, Pencil, Plus, Search, Settings, Sun, Trash2, X } from 'lucide-react';

const ICON = { light: Sun, dark: Moon, system: Monitor };
const NEXT = { light: 'dark', dark: 'system', system: 'light' };

export default function Sidebar({ open, onClose, conversations, activeId, onSelect, onNew, onRename, onDelete, query, onQuery, user, theme, onTheme, onSettings, onLogout }) {
  const [editing, setEditing] = useState(null);
  const [title, setTitle] = useState('');
  const [confirm, setConfirm] = useState(null);
  const inputRef = useRef(null);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);
  const ThemeIcon = ICON[theme];
  const commit = () => { if (title.trim()) onRename(editing, title.trim()); setEditing(null); };

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={onClose} aria-hidden="true" />}
      <aside aria-label="Conversations" className={`fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-slate-50 transition-all duration-200 dark:border-slate-800 dark:bg-slate-900 md:static ${open ? 'w-72 translate-x-0' : 'w-72 -translate-x-full md:w-0 md:translate-x-0 md:border-r-0'}`}>
        <div className="flex w-72 flex-1 flex-col overflow-hidden">
          <div className="flex items-center gap-2 p-3">
            <button className="btn-primary flex-1" onClick={onNew}><Plus size={16} /> New chat</button>
            <button className="btn-icon md:hidden" onClick={onClose} aria-label="Close sidebar"><X size={18} /></button>
          </div>
          <div className="px-3 pb-2">
            <div className="relative">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Search conversations" aria-label="Search conversations" className="input !py-2 pl-9" />
            </div>
          </div>
          <nav className="scroll-thin flex-1 overflow-y-auto px-2 pb-2">
            {conversations.length === 0 && <p className="px-3 py-6 text-center text-xs text-slate-500">{query ? 'No matching conversations.' : 'No conversations yet.'}</p>}
            <ul className="space-y-0.5">
              {conversations.map((c) => (
                <li key={c.id} className={`group flex items-center rounded-lg ${c.id === activeId ? 'bg-brand-100 dark:bg-slate-800' : 'hover:bg-slate-200/60 dark:hover:bg-slate-800/60'}`}>
                  {editing === c.id ? (
                    <div className="flex w-full items-center gap-1 p-1">
                      <input ref={inputRef} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-label="Conversation title" className="input !py-1.5" onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(null); }} />
                      <button className="btn-icon h-8 w-8" onClick={commit} aria-label="Save title"><Check size={15} /></button>
                    </div>
                  ) : confirm === c.id ? (
                    <div className="flex w-full items-center justify-between gap-1 px-3 py-2 text-sm">
                      <span className="text-red-600">Delete?</span>
                      <span className="flex gap-1">
                        <button className="rounded bg-red-600 px-2 py-0.5 text-xs text-white" onClick={() => { onDelete(c.id); setConfirm(null); }}>Delete</button>
                        <button className="rounded border px-2 py-0.5 text-xs dark:border-slate-600" onClick={() => setConfirm(null)}>Cancel</button>
                      </span>
                    </div>
                  ) : (
                    <>
                      <button onClick={() => onSelect(c.id)} className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm" aria-current={c.id === activeId ? 'page' : undefined} title={c.title}>{c.title}</button>
                      <span className="flex pr-1 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                        <button className="btn-icon h-7 w-7" onClick={() => { setEditing(c.id); setTitle(c.title); }} aria-label={`Rename ${c.title}`}><Pencil size={13} /></button>
                        <button className="btn-icon h-7 w-7 hover:!text-red-600" onClick={() => setConfirm(c.id)} aria-label={`Delete ${c.title}`}><Trash2 size={13} /></button>
                      </span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </nav>
          <div className="border-t border-slate-200 p-2 dark:border-slate-800">
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="min-w-0 truncate text-xs text-slate-500" title={user.email}>{user.display_name || user.email}</span>
              <span className="flex">
                <button className="btn-icon h-8 w-8" onClick={() => onTheme(NEXT[theme])} aria-label={`Theme: ${theme}. Switch theme`} title={`Theme: ${theme}`}><ThemeIcon size={16} /></button>
                <button className="btn-icon h-8 w-8" onClick={onSettings} aria-label="Settings" title="Settings"><Settings size={16} /></button>
                <button className="btn-icon h-8 w-8" onClick={onLogout} aria-label="Sign out" title="Sign out"><LogOut size={16} /></button>
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
