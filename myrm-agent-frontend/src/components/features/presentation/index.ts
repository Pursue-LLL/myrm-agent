/**
 * [INPUT]
 * Internal components from ./PresentationSlideCard, ./PresentationSlidePreviewViewer, ./PresentationGeneratorModal, ./PresentationTrigger
 *
 * [OUTPUT]
 * - PresentationSlideCard, PresentationSlideCardProps
 * - PresentationSlidePreviewViewer, PresentationSlidePreviewViewerProps
 * - PresentationGeneratorModal, PresentationGeneratorModalProps
 * - PresentationTrigger
 *
 * [POS]
 * Public facade of the Presentation suite (Item 16).
 * Single file < 40 lines. Zero `any` types.
 */

export { PresentationSlideCard } from './PresentationSlideCard';
export type { PresentationSlideCardProps } from './PresentationSlideCard';

export { PresentationSlidePreviewViewer } from './PresentationSlidePreviewViewer';
export type { PresentationSlidePreviewViewerProps } from './PresentationSlidePreviewViewer';

export { PresentationGeneratorModal } from './PresentationGeneratorModal';
export type { PresentationGeneratorModalProps } from './PresentationGeneratorModal';

export { PresentationTrigger } from './PresentationTrigger';
