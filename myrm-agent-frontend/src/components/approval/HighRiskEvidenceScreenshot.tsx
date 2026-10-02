'use client';

import React from 'react';
import { useTranslations } from 'next-intl';

interface HighRiskEvidenceScreenshotProps {
  /** Base64 JPEG evidence screenshot captured at interception time. */
  screenshotBase64: string;
  /** Original screenshot width in image space. */
  screenshotWidth: number;
  /** Original screenshot height in image space. */
  screenshotHeight: number;
  /** Target landing point X in image space (undefined = annotate without a point). */
  highlightX?: number;
  /** Target landing point Y in image space (undefined = annotate without a point). */
  highlightY?: number;
}

/**
 * High-risk action evidence card: the screen at interception time with the
 * destructive target circled. The red ring is placed with percentage
 * coordinates so it stays anchored to the target at any rendered size
 * (mobile narrow screens included) without any JS measurement.
 */
export default function HighRiskEvidenceScreenshot({
  screenshotBase64,
  screenshotWidth,
  screenshotHeight,
  highlightX,
  highlightY,
}: HighRiskEvidenceScreenshotProps) {
  const t = useTranslations('toolApproval');

  if (!screenshotBase64 || screenshotWidth <= 0 || screenshotHeight <= 0) {
    return null;
  }

  const hasHighlight = highlightX !== undefined && highlightY !== undefined;
  const leftPercent = hasHighlight ? (highlightX / screenshotWidth) * 100 : 0;
  const topPercent = hasHighlight ? (highlightY / screenshotHeight) * 100 : 0;
  // Ring radius in rendered pixels: fixed for consistent prominence across sizes.
  const RING_RADIUS = 28;

  return (
    <div className="rounded-lg border bg-muted/50 p-3">
      <div className="text-xs font-medium text-muted-foreground mb-2">{t('evidenceScreenshot')}</div>
      <div className="relative inline-block max-w-full overflow-hidden rounded-md border bg-background">
        <img
          src={`data:image/jpeg;base64,${screenshotBase64}`}
          alt={t('evidenceScreenshot')}
          className="block max-w-full h-auto select-none"
          draggable={false}
        />
        {hasHighlight && (
          <div
            className="pointer-events-none absolute rounded-full border-[3px] border-destructive bg-destructive/10 shadow-[0_0_0_5px_hsl(var(--destructive)/0.15)]"
            style={{
              left: `calc(${leftPercent}% - ${RING_RADIUS}px)`,
              top: `calc(${topPercent}% - ${RING_RADIUS}px)`,
              width: `${RING_RADIUS * 2}px`,
              height: `${RING_RADIUS * 2}px`,
            }}
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  );
}
