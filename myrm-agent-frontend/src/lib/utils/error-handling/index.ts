/**
 * [POS]
 * Error-handling domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export { errorManager } from './errorManager';
export {
  REDACTION_MASK,
  maskToken,
  redactErrorMessage,
  redactErrorObject,
  redactErrorPayload,
} from './errorRedactor';
export { mapSkillErrorToTranslationKey, getFriendlyErrorMessage } from './skillErrorMapper';
export { redactSensitiveClientText, containsSensitiveData } from './clientRedact';
