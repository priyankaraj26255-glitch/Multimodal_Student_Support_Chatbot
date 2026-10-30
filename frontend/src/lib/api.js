const BASE = import.meta.env.VITE_API_BASE || '/api';
let token = localStorage.getItem('token');
let onUnauthorized = () => {};

export const setToken = (t) => {
  token = t;
  if (t) localStorage.setItem('token', t);
  else localStorage.removeItem('token');
};
export const hasToken = () => !!token;
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };
export const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function errorMessage(res) {
  try {
    const j = await res.json();
    if (typeof j.detail === 'string') return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((d) => d.msg).join('; ');
  } catch { /* not json */ }
  if (res.status === 413) return 'The file or request is too large.';
  return `Request failed (${res.status}).`;
}

export async function request(path, { method = 'GET', body, raw = false, signal } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload = body;
  if (body !== undefined && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: payload, signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError('Cannot reach the server. Check your connection and that the backend is running.', 0);
  }
  if (res.status === 401 && !path.startsWith('/auth/')) onUnauthorized();
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

/** POST and consume a Server-Sent-Events stream. */
export async function streamSSE(path, body, onEvent, signal) {
  const res = await request(path, { method: 'POST', body: body ?? {}, raw: true, signal });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      let event = 'message';
      const data = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data.push(line.slice(5).trim());
      }
      if (data.length) onEvent(event, JSON.parse(data.join('\n')));
    }
  }
}

export function uploadFile(file, onProgress, signal) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', BASE + '/files/upload');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(new ApiError('Upload failed – cannot reach the server.', 0));
    xhr.onload = () => {
      let json = null;
      try { json = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(json);
      const d = json?.detail;
      reject(new ApiError(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : `Upload failed (${xhr.status}).`, xhr.status));
    };
    if (signal) signal.addEventListener('abort', () => { xhr.abort(); reject(new DOMException('Aborted', 'AbortError')); });
    const fd = new FormData();
    fd.append('file', file);
    xhr.send(fd);
  });
}

const blobCache = new Map();
export async function fileBlobUrl(id) {
  if (blobCache.has(id)) return blobCache.get(id);
  const res = await request(`/files/${id}/content`, { raw: true });
  const url = URL.createObjectURL(await res.blob());
  blobCache.set(id, url);
  return url;
}

export const api = {
  register: (b) => request('/auth/register', { method: 'POST', body: b }),
  login: (b) => request('/auth/login', { method: 'POST', body: b }),
  me: () => request('/auth/me'),
  capabilities: () => request('/capabilities'),
  conversations: (q) => request('/conversations' + (q ? `?q=${encodeURIComponent(q)}` : '')),
  createConversation: (b = {}) => request('/conversations', { method: 'POST', body: b }),
  getConversation: (id) => request(`/conversations/${id}`),
  updateConversation: (id, b) => request(`/conversations/${id}`, { method: 'PATCH', body: b }),
  deleteConversation: (id) => request(`/conversations/${id}`, { method: 'DELETE' }),
  upload: uploadFile,
  deleteFile: (id) => request(`/files/${id}`, { method: 'DELETE' }),
  fileText: (id) => request(`/files/${id}/text`),
  saveFileText: (id, text) => request(`/files/${id}/text`, { method: 'PUT', body: { text } }),
  runOcr: (id, engine) => request(`/files/${id}/ocr`, { method: 'POST', body: { engine } }),
  preferences: () => request('/preferences'),
  savePreferences: (b) => request('/preferences', { method: 'PUT', body: b }),
  deleteHistory: () => request('/me/history', { method: 'DELETE' }),
  deleteAccount: () => request('/me', { method: 'DELETE' }),
  async transcribe(blob, language) {
    const fd = new FormData();
    const ext = blob.type.includes('mp4') ? 'mp4' : blob.type.includes('ogg') ? 'ogg' : 'webm';
    fd.append('audio', blob, `speech.${ext}`);
    if (language && language !== 'auto') fd.append('language', language);
    return request('/audio/transcribe', { method: 'POST', body: fd });
  },
  async speech(text, voice) {
    const res = await request('/audio/speech', { method: 'POST', body: { text, voice }, raw: true });
    return res.blob();
  },
};
