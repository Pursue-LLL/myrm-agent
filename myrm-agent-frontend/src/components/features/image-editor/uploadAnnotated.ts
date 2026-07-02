import { uploadFiles } from '@/services/file';
import useChatStore from '@/store/useChatStore';

export async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error('Failed to read annotated image'));
    reader.readAsDataURL(blob);
  });
}

/**
 * Uploads an annotated image blob and inserts it into the current chat as an attachment.
 * Shared by ToolImageGallery and MediaPreview integration points.
 */
export async function uploadAnnotatedImage(blob: Blob): Promise<void> {
  const file = new File([blob], `annotated_${Date.now()}.png`, { type: 'image/png' });
  const result = await uploadFiles([file]);
  if (result.uploaded_count > 0 && result.files?.[0]) {
    const { files, setFiles } = useChatStore.getState();
    setFiles([...files, {
      fileName: result.files[0].fileName,
      fileExtension: 'png',
      fileUrl: result.files[0].fileUrl,
      fileType: 'uploaded',
    }]);
  }
}
