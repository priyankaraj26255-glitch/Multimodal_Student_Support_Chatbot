import { useCallback, useEffect, useRef, useState } from 'react';

export const voiceSupported = () => !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);

/** Browser microphone recorder. start() resolves to an error string or null. */
export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recRef = useRef(null);
  const chunks = useRef([]);
  const streamRef = useRef(null);
  const timer = useRef(null);

  const cleanup = () => {
    clearInterval(timer.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setRecording(false);
  };
  useEffect(() => cleanup, []);

  const start = useCallback(async () => {
    if (!voiceSupported()) return 'Voice input is not supported in this browser (or the page is not served over HTTPS/localhost). Please type instead.';
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find((m) => MediaRecorder.isTypeSupported(m));
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.start();
      recRef.current = rec;
      setSeconds(0);
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000);
      setRecording(true);
      return null;
    } catch (e) {
      cleanup();
      if (e.name === 'NotAllowedError' || e.name === 'SecurityError') return 'Microphone permission was denied. Allow microphone access in your browser settings, or type your message instead.';
      if (e.name === 'NotFoundError') return 'No microphone was found on this device. Please type your message instead.';
      return 'Could not start recording. Please type your message instead.';
    }
  }, []);

  const stop = useCallback(() => new Promise((resolve) => {
    const rec = recRef.current;
    if (!rec || rec.state === 'inactive') { cleanup(); return resolve(null); }
    rec.onstop = () => {
      const blob = new Blob(chunks.current, { type: rec.mimeType || 'audio/webm' });
      cleanup();
      resolve(blob.size > 500 ? blob : null);
    };
    rec.stop();
  }), []);

  return { recording, seconds, start, stop };
}
