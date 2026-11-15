/**
 * [INPUT]
 * @/services/file::uploadFiles (POS: HTTP upload client of the server)
 * @/lib/utils/fileUtils::{getMimeType,isImageFile} (POS: Extension classification and media types)
 * @/lib/utils/imageAdmission::admitAndCompressFiles (POS: Size admission and light compression of images before upload)
 * ./types::FileReference (POS: Platform-neutral file handle)
 *
 * [OUTPUT]
 * uploadPickedImages: Gives every picked local image a server copy and keeps its path on disk.
 *
 * [POS]
 * A desktop pick hands the app a path, not an upload, so the server never receives the image. The model sees an
 * attached image as a content block without a name; the workspace copy made from the upload is the only handle
 * it can pass to image_tool to edit that image. Pasted and dragged images already take this route.
 * Reading the bytes is injected so the platform file service stays the only code that touches the disk.
 */

import { getMimeType, isImageFile } from '@/lib/utils/fileUtils';
import { admitAndCompressFiles } from '@/lib/utils/imageAdmission';
import { uploadFiles, type UploadOptions } from '@/services/file';
import type { FileReference } from './types';

/**
 * Uploads the local images among `refs` and returns `refs` in the same order, each uploaded image carrying the
 * server file id and URL next to its local path. Files that are not local images pass through untouched.
 * Throws when the server did not keep every image, so the caller never mistakes a partial upload for a full one.
 */
export async function uploadPickedImages(
  refs: FileReference[],
  readBytes: (ref: FileReference) => Promise<Uint8Array>,
  options?: UploadOptions,
  signal?: AbortSignal,
): Promise<FileReference[]> {
  const imageIndexes = refs.flatMap((ref, index) => (ref.localPath && isImageFile(ref.fileExtension) ? [index] : []));
  if (imageIndexes.length === 0) {
    return refs;
  }

  const picked = await Promise.all(
    imageIndexes.map(async (index) => {
      const ref = refs[index];
      return new File([new Uint8Array(await readBytes(ref))], ref.fileName, { type: getMimeType(ref.fileExtension) });
    }),
  );
  const admitted = await admitAndCompressFiles(picked);
  const { files: uploaded } = await uploadFiles(admitted, signal, options);
  if (uploaded.length !== admitted.length) {
    throw new Error(`The server kept ${uploaded.length} of ${admitted.length} images`);
  }

  const result = [...refs];
  imageIndexes.forEach((refIndex, position) => {
    result[refIndex] = { ...refs[refIndex], id: uploaded[position].fileId, fileUrl: uploaded[position].fileUrl };
  });
  return result;
}
