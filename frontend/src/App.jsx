import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { api, hasToken, setToken, setUnauthorizedHandler, uid } from './lib/api.js';
import { useTheme } from './hooks/useTheme.js';
import { useAudioPlayer } from './hooks/useAudioPlayer.js';
import AuthPage from './components/AuthPage.jsx';
import Sidebar from './components/Sidebar.jsx';
import ChatView from './components/ChatView.jsx';
import SettingsModal from './components/SettingsModal.jsx';
import TextModal from './components/TextModal.jsx';
import AudioBar from './components/AudioBar.jsx';
import Toasts from './components/Toasts.jsx';

export default function App() {
  const [theme, setTheme] = useTheme();
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(hasToken());
  const [prefs, setPrefs] = useState(null);
  const [caps, setCaps] = useState(null);
  const [convs, setConvs] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [query, setQuery] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 768);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [reviewFile, setReviewFile] = useState(null);
  const [toasts, setToasts] = useState([]);

  const toast = useCallback((message, type = 'success') => {
    const id = uid();
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === 'error' ? 7000 : 3500);
  }, []);
  const player = useAudioPlayer(toast, prefs?.tts_voice);

  const loadConvs = useCallback((q = '') => api.conversations(q).then(setConvs).catch(() => {}), []);

  const init = useCallback(async () => {
    const [p, c, list] = await Promise.all([api.preferences(), api.capabilities(), api.conversations()]);
    setPrefs(p); setCaps(c); setConvs(list);
  }, []);

  const logout = useCallback((msg) => {
    setToken(null); setUser(null); setPrefs(null); setConvs([]); setActiveId(null); setQuery('');
    player.stop();
    if (msg) toast(msg, 'error');
  }, [player, toast]);

  useEffect(() => { setUnauthorizedHandler(() => logout('Your session expired. Please sign in again.')); }, [logout]);

  useEffect(() => {
    if (!hasToken()) return;
    api.me().then(async (u) => { setUser(u); await init(); }).catch(() => setToken(null)).finally(() => setBooting(false));
  }, [init]);

  useEffect(() => {
    if (!user) return;
    const t = setTimeout(() => loadConvs(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query, user, loadConvs]);

  const onAuth = async (res) => {
    setToken(res.access_token);
    setUser(res.user);
    try { await init(); } catch (e) { toast(e.message, 'error'); }
  };

  const closeIfMobile = () => window.innerWidth < 768 && setSidebarOpen(false);

  if (booting) return <div className="flex h-full items-center justify-center"><Loader2 className="animate-spin text-slate-400" /></div>;
  if (!user || !prefs) return <><AuthPage onAuth={onAuth} /><Toasts toasts={toasts} dismiss={(id) => setToasts((t) => t.filter((x) => x.id !== id))} /></>;

  const active = convs.find((c) => c.id === activeId);

  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} conversations={convs} activeId={activeId}
        onSelect={(id) => { setActiveId(id); closeIfMobile(); }} onNew={() => { setActiveId(null); closeIfMobile(); }}
        onRename={async (id, title) => { try { await api.updateConversation(id, { title }); setConvs((cs) => cs.map((c) => (c.id === id ? { ...c, title } : c))); } catch (e) { toast(e.message, 'error'); } }}
        onDelete={async (id) => { try { await api.deleteConversation(id); if (id === activeId) setActiveId(null); loadConvs(query.trim()); } catch (e) { toast(e.message, 'error'); } }}
        query={query} onQuery={setQuery} user={user} theme={theme} onTheme={setTheme}
        onSettings={() => setSettingsOpen(true)} onLogout={() => logout()} />
      <main className="flex min-w-0 flex-1 flex-col">
        <ChatView convId={activeId} title={active?.title} prefs={prefs} caps={caps} toast={toast} player={player} user={user}
          onCreated={(c) => { setActiveId(c.id); setConvs((cs) => [c, ...cs]); }} onListChanged={() => loadConvs(query.trim())}
          onReview={setReviewFile} onToggleSidebar={() => setSidebarOpen((o) => !o)} />
      </main>
      <AudioBar player={player} />
      {settingsOpen && <SettingsModal prefs={prefs} caps={caps} toast={toast} onClose={() => setSettingsOpen(false)} onSaved={setPrefs}
        onHistoryDeleted={() => { setActiveId(null); setConvs([]); }} onAccountDeleted={() => { logout(); toast('Your account and data were deleted.'); }} />}
      {reviewFile && <TextModal file={reviewFile} toast={toast} onClose={() => setReviewFile(null)} />}
      <Toasts toasts={toasts} dismiss={(id) => setToasts((t) => t.filter((x) => x.id !== id))} />
    </div>
  );
}
