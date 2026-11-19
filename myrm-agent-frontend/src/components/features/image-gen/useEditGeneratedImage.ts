'use client';

/**
 * [INPUT]
 * @/store/useChatStore (POS: Composer state: attached files and the draft message)
 * @/lib/api-url::getStorageUrl (POS: Turns a stored-media reference into a URL the browser can load)
 * @/lib/mediaReference::parseMediaReference (POS: Reads the id out of a `media://<id>` reference)
 * @/lib/chat/focusMessageInput (POS: Cursor placement in the message box)
 * @/lib/utils/fileUtils::isImageFile (POS: Extension classification)
 * ./ImageResultCard::ImageGenImage (POS: The image a card hands back when the user asks to edit it)
 *
 * [OUTPUT]
 * useEditGeneratedImage: Handler that puts one generated image into the composer as an attachment and prefills the
 * edit instruction, so the next message edits exactly that image.
 *
 * [POS]
 * The edit-this-image action shared by every card that shows a generated image. The attachment names the media
 * (`mediaId`) instead of carrying an upload id: the message builder turns it into a `media://<id>` reference the
 * model can pass straight to the image tool.
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { focusMessageInput } from '@/lib/chat/focusMessageInput';
import { getStorageUrl } from '@/lib/api-url';
import { parseMediaReference } from '@/lib/mediaReference';
import { isImageFile } from '@/lib/utils/fileUtils';
import type { File } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import type { ImageGenImage } from './ImageResultCard';

function imageExtension(mimeType: string | undefined): string {
  const subtype = mimeType?.split('/')[1]?.split(';')[0]?.trim().toLowerCase();
  const extension = subtype === 'jpeg' ? 'jpg' : subtype;
  return extension && isImageFile(extension) ? extension : 'png';
}

function generatedImageAttachment(mediaId: string, image: ImageGenImage): File {
  const extension = imageExtension(image.mimeType);
  return {
    fileName: `${mediaId}.${extension}`,
    fileExtension: extension,
    fileUrl: getStorageUrl(image.url),
    fileType: 'uploaded',
    status: 'ready',
    mediaId,
  };
}

export function useEditGeneratedImage(): (image: ImageGenImage) => void {
  const t = useTranslations('imageGen');

  return useCallback(
    (image) => {
      const mediaId = parseMediaReference(image.url);
      if (!mediaId) {
        return;
      }
      const { setFiles, inputMessage, setInputMessage } = useChatStore.getState();
      setFiles((files) =>
        files.some((file) => file.mediaId === mediaId) ? files : [...files, generatedImageAttachment(mediaId, image)],
      );
      // Text the user already typed stays: the instruction they are writing is more specific than the prefix.
      if (!inputMessage.trim()) {
        setInputMessage(t('editPromptPrefix'));
      }
      focusMessageInput();
    },
    [t],
  );
}
