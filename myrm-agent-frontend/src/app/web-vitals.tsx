'use client';

import { useReportWebVitals } from 'next/web-vitals';

export function WebVitals() {
  useReportWebVitals((metric) => {
    // 发送到分析服务（如需要可以集成Google Analytics或自建服务）
    console.log('[Web Vitals]', metric);

    // 可选：发送到后端API进行存储和分析
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'production') {
      try {
        fetch('/api/v1/analytics/web-vitals', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(metric),
          keepalive: true,
        }).catch(() => {
          // 静默失败，不影响用户体验
        });
      } catch {
        // 静默失败
      }
    }
  });

  return null;
}
