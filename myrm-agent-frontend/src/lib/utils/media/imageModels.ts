/**
 * [OUTPUT]
 * - ImageModelOption, IMAGE_MODEL_OPTIONS
 * - isImageModelSelected
 *
 * [POS]
 * The image models the settings page offers. The ids are the generation engine's own model profiles
 * (`image_models` of `shared/config/media_generation_contract.json`, held against the engine by a server test), so
 * every choice here is one the engine can run. A stored model outside this list, such as one the vendor has retired,
 * counts as nothing chosen.
 */

export interface ImageModelOption {
  value: string;
  label: string;
  description: string;
}

export const IMAGE_MODEL_OPTIONS: ImageModelOption[] = [
  { value: 'gpt-image-2.6-sunburst', label: 'GPT Image 2.6 Sunburst', description: 'OpenAI' },
  { value: 'gpt-image-2.6-flare', label: 'GPT Image 2.6 Flare', description: 'OpenAI' },
  { value: 'gemini/imagen-3.0-generate-002', label: 'Imagen 3.0', description: 'Google' },
  { value: 'flux/schnell', label: 'Flux Schnell', description: 'Together AI' },
  { value: 'flux/pro', label: 'Flux Pro', description: 'Together AI' },
  { value: 'stability/stable-diffusion-xl', label: 'SDXL', description: 'Stability AI' },
  { value: 'xai/grok-imagine-image', label: 'Grok Imagine', description: 'xAI' },
  { value: 'xai/grok-imagine-image-quality', label: 'Grok Imagine Quality', description: 'xAI' },
];

export const isImageModelSelected = (model: string | undefined): model is string =>
  IMAGE_MODEL_OPTIONS.some((option) => option.value === model);
