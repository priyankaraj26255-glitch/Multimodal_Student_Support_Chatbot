import { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { fileBlobUrl } from '../lib/api.js';

/** <img> for protected files: fetched with the auth header, shown via a blob URL. */
export default function AuthedImage({ id, alt, className = '' }) {
  const [src, setSrc] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    fileBlobUrl(id).then((u) => alive && setSrc(u)).catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, [id]);
  if (failed) return <div className={`flex items-center justify-center bg-slate-100 text-slate-400 dark:bg-slate-800 ${className}`} title="Image no longer available"><ImageOff size={18} /></div>;
  if (!src) return <div className={`animate-pulse bg-slate-200 dark:bg-slate-800 ${className}`} />;
  return <img src={src} alt={alt} className={className} />;
}
