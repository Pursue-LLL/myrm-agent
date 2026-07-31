/**
 * [INPUT]
 * @/services/i18nToastService::translateI18nKey (POS: store-safe i18n lookup)
 * @/lib/utils/toast::toast (POS: unified toast wrapper)
 *
 * [OUTPUT]
 * VISION_SETTINGS_PATH, resolveVisionConfigGapActionLabel, runVisionConfigGapAction,
 * showVisionNotConfiguredToast
 *
 * [POS]
 * SSOT for vision capability config-gap CTA (attach/upload warnings). Mirrors webSearchConfigGap.
 */

import { toast } from '@/lib/utils/toast';
import { translateI18nKey } from '@/services/i18nToastService';

/** Default settings path for vision fallback configuration. */
export const VISION_SETTINGS_PATH = '/settings/models?sub=default';

const VISION_GAP_I18N = {
  image: {
    title: 'chat.visionNotConfigured.imageTitle',
    description: 'chat.visionNotConfigured.imageDescription',
  },
  video: {
    title: 'chat.visionNotConfigured.videoTitle',
    description: 'chat.visionNotConfigured.videoDescription',
  },
  action: 'chat.visionNotConfigured.action',
} as const;

export type VisionConfigGapKind = keyof typeof VISION_GAP_I18N;

const VISION_GAP_FALLBACKS: Record<string, { en: string; zh: string }> = {
  [VISION_GAP_I18N.image.title]: {
    en: 'Images need a vision model',
    zh: '当前配置无法读图',
  },
  [VISION_GAP_I18N.image.description]: {
    en: 'Configure a vision fallback model in Settings to analyze images with a text-only primary model.',
    zh: '请在设置中配置视觉降级模型，以便在纯文本主模型下分析图片。',
  },
  [VISION_GAP_I18N.video.title]: {
    en: 'Videos need a vision model',
    zh: '当前配置无法读视频',
  },
  [VISION_GAP_I18N.video.description]: {
    en: 'Configure a vision fallback model in Settings to analyze videos.',
    zh: '请在设置中配置视觉降级模型以分析视频。',
  },
  [VISION_GAP_I18N.action]: {
    en: 'Go to Settings',
    zh: '前往设置',
  },
};

function resolveVisionGapText(key: string, isZh: boolean): string {
  const fallbacks = VISION_GAP_FALLBACKS[key];
  if (!fallbacks) return key;
  return translateI18nKey(key, isZh ? fallbacks.zh : fallbacks.en);
}

/** Resolve CTA label for vision config gap toasts. */
export function resolveVisionConfigGapActionLabel(isZh?: boolean): string {
  const zh =
    isZh ?? (typeof document !== 'undefined' && document.documentElement.lang.startsWith('zh'));
  return resolveVisionGapText(VISION_GAP_I18N.action, zh);
}

/** Navigate to vision fallback settings. */
export async function runVisionConfigGapAction(
  settingsPath: string = VISION_SETTINGS_PATH,
): Promise<void> {
  if (typeof window !== 'undefined') {
    window.location.assign(settingsPath);
  }
}

/** Show attach/upload warning with Settings deep link when vision capability is missing. */
export function showVisionNotConfiguredToast(kind: VisionConfigGapKind): void {
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');
  const keys = VISION_GAP_I18N[kind];
  const title = resolveVisionGapText(keys.title, isZh);
  const description = resolveVisionGapText(keys.description, isZh);

  toast.warning(title, {
    description,
    duration: 6000,
    action: {
      label: resolveVisionConfigGapActionLabel(isZh),
      onClick: () => {
        void runVisionConfigGapAction();
      },
    },
  });
}
