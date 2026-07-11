import { BOOT_SCREEN_STORAGE_KEY } from '@/lib/local-backend-dev';

export function shouldShowBootScreen(): boolean {
  if (typeof window === 'undefined') return false;
  return !sessionStorage.getItem(BOOT_SCREEN_STORAGE_KEY);
}

export function markBootScreenShown(): void {
  try {
    sessionStorage.setItem(BOOT_SCREEN_STORAGE_KEY, '1');
  } catch {
    // sessionStorage unavailable
  }
}
