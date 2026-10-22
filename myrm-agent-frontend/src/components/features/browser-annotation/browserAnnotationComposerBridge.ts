/**
 * [INPUT]
 * ./browserAnnotationTypes (POS: AnnotationExportPayload)
 *
 * [OUTPUT]
 * dispatchAnnotationToComposer, subscribeComposerAnnotation
 *
 * [POS]
 * Event bridge for transmitting structured annotation payloads from browser preview to composer input.
 */

import type { AnnotationExportPayload } from './browserAnnotationTypes';

export const COMPOSER_ANNOTATION_EVENT = 'myrm:inject-composer-annotation';

export function dispatchAnnotationToComposer(payload: AnnotationExportPayload): void {
  if (typeof window === 'undefined') {
    return;
  }

  const event = new CustomEvent<AnnotationExportPayload>(COMPOSER_ANNOTATION_EVENT, {
    detail: payload,
    bubbles: true,
  });

  window.dispatchEvent(event);
}

export function subscribeComposerAnnotation(
  callback: (payload: AnnotationExportPayload) => void,
): () => void {
  if (typeof window === 'undefined') {
    return () => {};
  }

  const handler = (event: Event) => {
    const customEvent = event as CustomEvent<AnnotationExportPayload>;
    if (customEvent.detail) {
      callback(customEvent.detail);
    }
  };

  window.addEventListener(COMPOSER_ANNOTATION_EVENT, handler);

  return () => {
    window.removeEventListener(COMPOSER_ANNOTATION_EVENT, handler);
  };
}
