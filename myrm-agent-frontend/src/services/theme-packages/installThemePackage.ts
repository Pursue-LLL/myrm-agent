import { apiRequest } from '@/lib/api';
import type { ThemeProfileRecipe } from '@/theme-engine/schema';

export interface ThemePackageInstallResult {
  profile: ThemeProfileRecipe;
  setActive: boolean;
}

export async function installThemePackage(params: {
  sessionId: string;
  setActive: boolean;
  existingProfileIds: string[];
}): Promise<ThemePackageInstallResult> {
  const response = await apiRequest<{ install: ThemePackageInstallResult }>('/theme/packages/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sessionId: params.sessionId,
      setActive: params.setActive,
      existingProfileIds: params.existingProfileIds,
    }),
  });
  return response.install;
}
