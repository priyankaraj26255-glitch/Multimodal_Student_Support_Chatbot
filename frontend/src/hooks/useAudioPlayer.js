import { useCallback, useRef, useState } from 'react';
import { api } from '../lib/api.js';

/** Text-to-speech playback with play/pause/stop, mute and speed controls. */
export function useAudioPlayer(toast, voice) {
  const audio = useRef(null);
  const url = useRef(null);
  const req = useRef(0);
  const [state, setState] = useState({ status: 'idle', id: null });
  const [muted, setMutedState] = useState(false);
  const [rate, setRateState] = useState(1);

  const el = () => {
    if (!audio.current) {
      const a = new Audio();
      a.onended = () => setState({ status: 'idle', id: null });
      audio.current = a;
    }
    return audio.current;
  };

  const stop = useCallback(() => {
    req.current++;
    const a = audio.current;
    if (a) { a.pause(); a.removeAttribute('src'); a.load(); }
    if (url.current) { URL.revokeObjectURL(url.current); url.current = null; }
    setState({ status: 'idle', id: null });
  }, []);

  const play = useCallback(async (text, id) => {
    stop();
    const my = ++req.current;
    setState({ status: 'loading', id });
    try {
      const blob = await api.speech(text, voice);
      if (my !== req.current) return;
      url.current = URL.createObjectURL(blob);
      const a = el();
      a.src = url.current;
      a.muted = muted;
      a.playbackRate = rate;
      await a.play();
      setState({ status: 'playing', id });
    } catch (e) {
      if (my === req.current) {
        setState({ status: 'idle', id: null });
        toast(e.name === 'NotAllowedError' ? 'Your browser blocked audio playback. Tap the speaker again.' : e.message || 'Could not play audio.', 'error');
      }
    }
  }, [muted, rate, stop, toast, voice]);

  const toggle = useCallback(() => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) { a.play(); setState((s) => ({ ...s, status: 'playing' })); }
    else { a.pause(); setState((s) => ({ ...s, status: 'paused' })); }
  }, []);

  const setMuted = (m) => { setMutedState(m); if (audio.current) audio.current.muted = m; };
  const setRate = (r) => { setRateState(r); if (audio.current) audio.current.playbackRate = r; };

  return { state, muted, rate, play, stop, toggle, setMuted, setRate };
}
