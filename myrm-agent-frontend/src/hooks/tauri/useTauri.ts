import { useState, useEffect } from 'react';

export function useTauri() {
  const [isTauri, setIsTauri] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
      setIsTauri(true);
    }
  }, []);

  return isTauri;
}
