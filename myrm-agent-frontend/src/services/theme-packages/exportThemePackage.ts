import { API_BASE_URL } from '@/lib/api';
import type { ThemeProfileRecipe } from '@/theme-engine/schema';

export async function exportThemePackage(profile: ThemeProfileRecipe): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/theme/packages/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ profile }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'Theme export failed');
  }
  return response.blob();
}

export function downloadThemePackageBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename.endsWith('.myrmtheme') ? filename : `${filename}.myrmtheme`;
  anchor.click();
  URL.revokeObjectURL(url);
}
