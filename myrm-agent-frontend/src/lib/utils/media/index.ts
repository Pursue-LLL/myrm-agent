/**
 * [POS]
 * Media provider domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export { IMAGE_MODEL_OPTIONS, isImageModelSelected } from './imageModels';
export type { ImageModelOption } from './imageModels';
export {
  collectMediaCredentialWarnings,
  imageToolSetup,
  providerHasActiveApiKey,
  ttsToolSetup,
  videoToolSetup,
} from './mediaCredentialReadiness';
export type { MediaCredentialWarning, MediaCredentialWarningTool, MediaToolSetup } from './mediaCredentialReadiness';
export {
  fetchMediaProviderStatus,
  resolveImageProviderId,
  VIDEO_PROVIDER_CONFIG_IDS,
  videoProviderConfigId,
} from './mediaProviderStatus';
export type { MediaProviderStatus } from './mediaProviderStatus';
export {
  isTtsProvider,
  isTtsSelected,
  readStoredChoices,
  TTS_MODEL_OPTIONS,
  TTS_PROVIDER_OPTIONS,
  TTS_VOICE_OPTIONS,
} from './ttsCatalog';
export type { StoredChoices, StoredVoice, TtsModelOption, TtsProviderId } from './ttsCatalog';
