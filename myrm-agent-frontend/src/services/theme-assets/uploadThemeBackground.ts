/**
 * Theme background upload orchestration (validate → poster → upload → file: refs).
 *
 * [INPUT]
 * @/theme-engine::validateThemeBackgroundFile, mediaKindFromFile
 * services/theme-assets/extractVideoPoster::extractVideoPosterBlob
 * services/theme-assets/uploadThemeAsset::uploadThemeAsset
 *
 * [OUTPUT]
 * uploadThemeBackground, ThemeBackgroundUploadResult, ThemeBackgroundValidationFailedError
 *
 * [POS]
 * SSOT for Settings AppearancePanel and Theme Studio ThemeMediaUploadField hero uploads.
 */
import {
  mediaKindFromFile,
  validateThemeBackgroundFile,
  type ThemeBackgroundValidationError,
  type ThemeMediaKind,
} from '@/theme-engine';
import { extractVideoPosterBlob } from './extractVideoPoster';
import { uploadThemeAsset } from './uploadThemeAsset';

export interface ThemeBackgroundUploadResult {
  assetRef: string;
  mediaKind: Exclude<ThemeMediaKind, 'none'>;
  posterAssetRef: string | null;
}

export class ThemeBackgroundValidationFailedError extends Error {
  readonly code: ThemeBackgroundValidationError;

  constructor(code: ThemeBackgroundValidationError) {
    super(code);
    this.name = 'ThemeBackgroundValidationFailedError';
    this.code = code;
  }
}

function toFileRef(fileId: string): string {
  return `file:${fileId}`;
}

function buildPosterFile(sourceFile: File, posterBlob: Blob): File {
  const posterName = sourceFile.name.replace(/\.mp4$/i, '') || 'workspace-background';
  return new File([posterBlob], `${posterName}-poster.jpg`, {
    type: 'image/jpeg',
  });
}

/** Validate, extract MP4 poster when needed, upload, return `file:` asset refs. */
export async function uploadThemeBackground(
  file: File,
  options?: { videoPosterBlob?: Blob },
): Promise<ThemeBackgroundUploadResult> {
  const validationError = validateThemeBackgroundFile(file);
  if (validationError) {
    throw new ThemeBackgroundValidationFailedError(validationError);
  }

  const mediaKind = mediaKindFromFile(file);

  if (mediaKind === 'video') {
    const posterBlob = options?.videoPosterBlob ?? (await extractVideoPosterBlob(file));
    const posterFile = buildPosterFile(file, posterBlob);
    const [uploaded, posterUploaded] = await Promise.all([uploadThemeAsset(file), uploadThemeAsset(posterFile)]);
    return {
      assetRef: toFileRef(uploaded.fileId),
      mediaKind,
      posterAssetRef: toFileRef(posterUploaded.fileId),
    };
  }

  const uploaded = await uploadThemeAsset(file);
  return {
    assetRef: toFileRef(uploaded.fileId),
    mediaKind,
    posterAssetRef: null,
  };
}
