import { Loader2, Pause, Play, Square, Volume2, VolumeX } from 'lucide-react';

const RATES = [1, 1.25, 1.5, 0.75];

export default function AudioBar({ player }) {
  const { state, muted, rate } = player;
  if (state.status === 'idle') return null;
  const loading = state.status === 'loading';
  return (
    <div role="region" aria-label="Audio playback" className="fixed bottom-24 left-1/2 z-40 flex -translate-x-1/2 items-center gap-1 rounded-full border border-slate-200 bg-white/95 px-2 py-1.5 shadow-lg backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
      {loading ? <Loader2 size={16} className="mx-2 animate-spin text-brand-600" /> : (
        <button className="btn-icon" onClick={player.toggle} aria-label={state.status === 'playing' ? 'Pause' : 'Play'}>
          {state.status === 'playing' ? <Pause size={16} /> : <Play size={16} />}
        </button>
      )}
      <span className="px-1 text-xs text-slate-500">{loading ? 'Preparing audio…' : 'Reading aloud'}</span>
      <button className="btn-icon" onClick={() => player.setMuted(!muted)} aria-label={muted ? 'Unmute' : 'Mute'}>{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</button>
      <button className="h-9 rounded-lg px-2 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" onClick={() => player.setRate(RATES[(RATES.indexOf(rate) + 1) % RATES.length])} aria-label={`Playback speed ${rate}x`}>{rate}×</button>
      <button className="btn-icon" onClick={player.stop} aria-label="Stop"><Square size={14} /></button>
    </div>
  );
}
