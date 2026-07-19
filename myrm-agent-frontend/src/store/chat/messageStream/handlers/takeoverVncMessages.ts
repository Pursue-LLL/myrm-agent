/**
 * [OUTPUT]
 * takeoverVncOpenFailedMessage: localized toast when managed VNC takeover POST fails.
 *
 * [POS]
 * SSE handler toast copy for browser takeover. Strings mirror billing.vnc.takeoverVncOpenFailed in locales/*.json.
 */

const TAKEOVER_VNC_OPEN_FAILED: Record<string, string> = {
  en: 'Unable to open the visual desktop for browser takeover. Reconnect or retry.',
  zh: '无法打开可视化桌面以接管浏览器，请重连或重试。',
  de: 'Visueller Desktop für Browser-Übernahme konnte nicht geöffnet werden. Bitte erneut verbinden oder wiederholen.',
  ja: 'ブラウザ引き継ぎ用のビジュアルデスクトップを開けませんでした。再接続するか、もう一度お試しください。',
  ko: '브라우저 인수를 위한 비주얼 데스크톱을 열 수 없습니다. 다시 연결하거나 재시도해주세요.',
};

export function takeoverVncOpenFailedMessage(locale: string | null): string {
  const key = locale?.split('-')[0] ?? 'en';
  return TAKEOVER_VNC_OPEN_FAILED[key] ?? TAKEOVER_VNC_OPEN_FAILED.en;
}
