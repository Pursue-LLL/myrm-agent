/**
 * [OUTPUT]
 * renderUiSurfaceUnavailableMessage: localized toast when inline UI is unavailable on this channel.
 *
 * [POS]
 * SSE gapEvents fallback copy for `capability_gap` + `reason=surface_unavailable`.
 * Strings mirror agent.configPanel.renderUiWebOnlyHint in locales/*.json.
 */

const RENDER_UI_SURFACE_UNAVAILABLE: Record<string, string> = {
  en: 'Inline interactive UI renders only in Web Chat and the desktop app. Telegram, scheduled tasks, and other channels cannot display inline forms or charts.',
  zh: '交互式 UI 仅在 Web 对话与桌面客户端内渲染；Telegram、定时任务等渠道无法显示内联表单或图表。',
  de: 'Interaktive UI wird nur im Web-Chat und in der Desktop-App gerendert. Telegram, geplante Aufgaben und andere Kanäle können keine Inline-Formulare oder Diagramme anzeigen.',
  ja: 'インライン UI は Web チャットとデスクトップアプリでのみ表示されます。Telegram、スケジュールタスク、その他のチャネルではインラインフォームやチャートを表示できません。',
  ko: '인라인 UI는 Web 채팅과 데스크톱 앱에서만 렌더링됩니다. Telegram, 예약 작업 및 기타 채널에서는 인라인 양식이나 차트를 표시할 수 없습니다.',
};

export function renderUiSurfaceUnavailableMessage(locale: string | null): string {
  const key = locale?.split('-')[0] ?? 'en';
  return RENDER_UI_SURFACE_UNAVAILABLE[key] ?? RENDER_UI_SURFACE_UNAVAILABLE.en;
}
