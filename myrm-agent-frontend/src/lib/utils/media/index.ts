/**
 * [POS]
 * Media provider domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export {
  collectMediaCredentialWarnings,
  isImageMediaCredentialReady,
  isTtsMediaCredentialReady,
  isVideoMediaCredentialReady,
  providerHasActiveApiKey,
} from './mediaCredentialReadiness';
export type { MediaCredentialWarningTool } from './mediaCredentialReadiness';
export { fetchMediaProviderStatus, resolveImageProviderId, VIDEO_PROVIDER_CONFIG_IDS } from './mediaProviderStatus';
export type { MediaProviderStatus } from './mediaProviderStatus';
