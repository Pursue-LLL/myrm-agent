/**
 * [INPUT]
 * - DesignerEyeOverlay from ./DesignerEyeOverlay
 * - DesignerEyeFeedbackModal from ./DesignerEyeFeedbackModal
 * - domSourceLocator from ./domSourceLocator
 *
 * [OUTPUT]
 * - Public exports for Designer's Eye UI Element Inspector & Self-Evolution Pipeline
 *
 * [POS]
 * Facade entry point for designer-eye feature module.
 */

export { DesignerEyeOverlay } from './DesignerEyeOverlay';
export { DesignerEyeFeedbackModal } from './DesignerEyeFeedbackModal';
export type { DesignerEyeFeedbackModalProps } from './DesignerEyeFeedbackModal';

export {
  normalizeSourceFilePath,
  buildConciseCssSelector,
  resolveFiberSource,
  extractComponentHierarchy,
  inferCandidateSourceFiles,
  extractInspectionFingerprint,
} from './domSourceLocator';

export type {
  SourceLocation,
  SourceConfidence,
  DomInspectionFingerprint,
} from './domSourceLocator';
