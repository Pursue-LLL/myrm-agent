/**
 * [INPUT]
 * ./browserAnnotationTypes (POS: PinBoundingBox)
 *
 * [OUTPUT]
 * cropImageFromBase64 (Canvas 2D offscreen cropping utility)
 *
 * [POS]
 * Image crop and local snapshot extraction helper for browser annotation pins.
 */

import type { PinBoundingBox } from './browserAnnotationTypes';

export async function cropImageFromBase64(
  base64Image: string,
  box: PinBoundingBox,
  padding = 16,
): Promise<string> {
  if (
    typeof window === 'undefined' ||
    typeof document === 'undefined' ||
    typeof HTMLCanvasElement === 'undefined'
  ) {
    return base64Image;
  }

  return new Promise((resolve) => {
    // Timeout fallback for headless/jsdom environments where Image.onload doesn't fire
    const fallbackTimer = setTimeout(() => {
      resolve(base64Image);
    }, 50);

    try {
      const img = new Image();
      img.crossOrigin = 'anonymous';

      img.onload = () => {
        clearTimeout(fallbackTimer);
        try {
          const naturalWidth = img.naturalWidth;
          const naturalHeight = img.naturalHeight;

          if (
            naturalWidth === 0 ||
            naturalHeight === 0 ||
            box.viewportWidth === 0 ||
            box.viewportHeight === 0
          ) {
            resolve(base64Image);
            return;
          }

          const scaleX = naturalWidth / box.viewportWidth;
          const scaleY = naturalHeight / box.viewportHeight;

          const rawX = box.x * scaleX;
          const rawY = box.y * scaleY;
          const rawW = box.width * scaleX;
          const rawH = box.height * scaleY;

          const padX = padding * scaleX;
          const padY = padding * scaleY;

          const cropX = Math.max(0, Math.floor(rawX - padX));
          const cropY = Math.max(0, Math.floor(rawY - padY));
          const cropW = Math.min(naturalWidth - cropX, Math.ceil(rawW + padX * 2));
          const cropH = Math.min(naturalHeight - cropY, Math.ceil(rawH + padY * 2));

          if (cropW <= 0 || cropH <= 0) {
            resolve(base64Image);
            return;
          }

          const canvas = document.createElement('canvas');
          canvas.width = cropW;
          canvas.height = cropH;

          const ctx = canvas.getContext('2d');
          if (!ctx) {
            resolve(base64Image);
            return;
          }

          ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);
          const croppedDataUrl = canvas.toDataURL('image/png', 0.92);
          resolve(croppedDataUrl);
        } catch {
          resolve(base64Image);
        }
      };

      img.onerror = () => {
        clearTimeout(fallbackTimer);
        resolve(base64Image);
      };

      if (base64Image.startsWith('data:')) {
        img.src = base64Image;
      } else {
        img.src = `data:image/png;base64,${base64Image}`;
      }
    } catch {
      clearTimeout(fallbackTimer);
      resolve(base64Image);
    }
  });
}
