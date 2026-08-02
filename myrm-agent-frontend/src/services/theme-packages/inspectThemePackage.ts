import { apiRequest } from '@/lib/api';

export interface ThemePackageInspectResult {
  sessionId: string;
  packageSha256: string;
  canImport: boolean;
  warnings: string[];
  signatureStatus: string;
  name: string;
  description: string | null;
  tagline: string | null;
  author: string | null;
  layoutId: string;
  fontId: string;
  mediaKind: string;
  wash: number;
  primaryLight: string;
  dualAccent: boolean;
  heroMime: string | null;
  heroThumbnailBase64: string | null;
  previewThumbnailBase64: string | null;
}

export async function inspectThemePackage(file: File): Promise<ThemePackageInspectResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiRequest<{ inspect: ThemePackageInspectResult }>('/theme/packages/inspect', {
    method: 'POST',
    body: formData,
  });
  return response.inspect;
}
