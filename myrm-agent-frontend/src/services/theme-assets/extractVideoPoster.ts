const POSTER_SEEK_SECONDS = 0.1;
const POSTER_JPEG_QUALITY = 0.92;
const POSTER_LOAD_TIMEOUT_MS = 30_000;

export class VideoPosterExtractionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'VideoPosterExtractionError';
  }
}

export async function extractVideoPosterBlob(file: File): Promise<Blob> {
  if (typeof document === 'undefined') {
    throw new VideoPosterExtractionError('Video poster extraction requires a browser environment');
  }

  return new Promise<Blob>((resolve, reject) => {
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.preload = 'auto';

    const objectUrl = URL.createObjectURL(file);
    let settled = false;

    const finish = (action: () => void) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      URL.revokeObjectURL(objectUrl);
      video.removeAttribute('src');
      video.load();
      action();
    };

    const timeoutId = window.setTimeout(() => {
      finish(() => reject(new VideoPosterExtractionError('Video poster extraction timed out')));
    }, POSTER_LOAD_TIMEOUT_MS);

    video.onloadeddata = () => {
      video.currentTime = POSTER_SEEK_SECONDS;
    };

    video.onseeked = () => {
      const width = video.videoWidth;
      const height = video.videoHeight;
      if (width <= 0 || height <= 0) {
        finish(() => reject(new VideoPosterExtractionError('Video has no readable frame dimensions')));
        return;
      }

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext('2d');
      if (!context) {
        finish(() => reject(new VideoPosterExtractionError('Canvas context unavailable')));
        return;
      }

      context.drawImage(video, 0, 0, width, height);
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            finish(() => reject(new VideoPosterExtractionError('Failed to encode poster frame')));
            return;
          }
          finish(() => resolve(blob));
        },
        'image/jpeg',
        POSTER_JPEG_QUALITY,
      );
    };

    video.onerror = () => {
      finish(() => reject(new VideoPosterExtractionError('Failed to load video for poster extraction')));
    };

    video.src = objectUrl;
    video.load();
  });
}
