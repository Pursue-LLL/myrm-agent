import { apiRequest } from '@/lib/api';

export interface ThemeAssetUploadFile {
  fileId: string;
  fileName: string;
  fileUrl: string;
  mimeType: string;
}

export interface ThemeAssetUploadResult {
  file: ThemeAssetUploadFile;
}

export async function uploadThemeAsset(file: File): Promise<ThemeAssetUploadFile> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiRequest<ThemeAssetUploadResult>('/theme/assets/upload', {
    method: 'POST',
    body: formData,
  });
  return response.file;
}
