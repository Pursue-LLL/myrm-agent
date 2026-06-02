import { apiRequest, getApiUrl } from '@/lib/api';

export interface UploadFileResponse {
  uploaded_count: number;
  files: Array<{
    fileId: string;
    fileName: string;
    fileUrl: string;
  }>;
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

export interface PDFImageItem {
  data: string;
  mimeType: string;
}

export interface PDFTableItem {
  pageNumber: number;
  tableIndex: number;
  data: string[][];
  id: string;
  markdown: string;
  summaryL0: string;
}

export interface PDFExtractResult {
  text: string;
  images: PDFImageItem[];
  pageCount: number;
  strategy: 'text' | 'image' | 'hybrid';
  tables: PDFTableItem[];
  imageTrace?: {
    totalProcessed: number;
    keptCount: number;
    droppedCount: number;
    dropReasons: Record<string, number>;
  };
}

interface RawUploadFile {
  file_id: string;
  file_name: string;
  file_url: string;
}

function mapUploadResponse(raw: { uploaded_count: number; files: RawUploadFile[] }): UploadFileResponse {
  return {
    uploaded_count: raw.uploaded_count,
    files: (raw.files || []).map((f) => ({
      fileId: f.file_id,
      fileName: f.file_name,
      fileUrl: f.file_url,
    })),
  };
}

export const uploadFiles = async (files: File[], signal?: AbortSignal): Promise<UploadFileResponse> => {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));

  const response = await apiRequest<{ uploaded_count: number; files: RawUploadFile[] }>('/files/upload', {
    method: 'POST',
    body: formData,
    headers: { Accept: 'application/json' },
    signal,
  });

  return mapUploadResponse(response);
};

export const uploadFilesWithProgress = (
  files: File[],
  onProgress: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<UploadFileResponse> => {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    const xhr = new XMLHttpRequest();

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException('Upload aborted', 'AbortError'));
        return;
      }
      signal.addEventListener(
        'abort',
        () => {
          xhr.abort();
          reject(new DOMException('Upload aborted', 'AbortError'));
        },
        { once: true },
      );
    }

    xhr.open('POST', getApiUrl('/files/upload'));

    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    xhr.setRequestHeader('Accept', 'application/json');

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress({
          loaded: e.loaded,
          total: e.total,
          percent: Math.min(100, Math.round((e.loaded / e.total) * 100)),
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const raw = JSON.parse(xhr.responseText);
          const data = raw.data || raw;
          if (!data || typeof data.uploaded_count !== 'number') {
            reject(new Error('Unexpected server response format'));
            return;
          }
          resolve(mapUploadResponse(data));
        } catch {
          reject(new Error('Invalid server response'));
        }
      } else {
        let errorMessage = `Upload failed: ${xhr.status}`;
        try {
          const errorData = JSON.parse(xhr.responseText);
          errorMessage = errorData.detail || errorData.message || errorData.error || errorMessage;
        } catch {
          if (xhr.responseText) {
            errorMessage = xhr.responseText;
          }
        }
        reject(new Error(errorMessage));
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(formData);
  });
};

export const extractPdfContent = async (
  params: { fileId: string } | { filePath: string },
): Promise<PDFExtractResult> => {
  return apiRequest<PDFExtractResult>('/files/extract-pdf', {
    method: 'POST',
    body: JSON.stringify(params),
  });
};

export interface DocumentExtractResult {
  text: string;
  format: string;
  charCount: number;
}

export const extractDocumentContent = async (
  params: { fileId: string } | { filePath: string },
): Promise<DocumentExtractResult> => {
  return apiRequest<DocumentExtractResult>('/files/extract-document', {
    method: 'POST',
    body: JSON.stringify(params),
  });
};
