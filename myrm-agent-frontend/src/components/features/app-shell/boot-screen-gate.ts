import { BOOT_SCREEN_STORAGE_KEY } from '@/lib/local-backend-dev';

function readBootShown(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(BOOT_SCREEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function shouldShowBootScreen(): boolean {
  if (typeof window === 'undefined') return false;
  return readBootShown() !== '1';
}

export function markBootScreenShown(): void {
  try {
    localStorage.setItem(BOOT_SCREEN_STORAGE_KEY, '1');
  } catch {
    // localStorage unavailable
  }
}
