/**
 * Agent panel ambient ink background — large fixed landscape blob, independent of gallery height.
 */

import { cn } from '@/lib/utils/classnameUtils';

type GalleryBackgroundVariant = 'panel' | 'section';

interface GalleryBackgroundProps {
  variant?: GalleryBackgroundVariant;
}

const PANEL_INK_PATH =
  'M40,50 C90,15 150,25 200,20 C280,12 350,30 420,25 C470,22 495,55 485,100 C490,140 480,190 460,230 C430,265 360,280 280,275 C200,278 120,270 60,255 C20,240 5,200 10,150 C8,100 15,70 40,50 Z';

const SECTION_INK_PATH =
  'M35,40 C80,15 140,25 200,20 C280,14 350,28 420,24 C465,21 490,50 480,90 C485,130 475,165 445,185 C390,200 300,195 200,190 C110,188 45,180 20,155 C5,130 10,85 35,40 Z';

const INK_SPOTS = (
  <g>
    <ellipse cx="470" cy="60" rx="25" ry="18" fill="var(--gallery-ink-spot-warm)" />
    <ellipse cx="30" cy="220" rx="22" ry="15" fill="var(--gallery-ink-spot)" />
    <circle cx="485" cy="180" r="18" fill="var(--gallery-ink-spot)" />
    <circle cx="15" cy="80" r="20" fill="var(--gallery-ink-spot-warm)" />
    <circle cx="495" cy="120" r="8" fill="var(--gallery-ink-spot)" />
    <circle cx="460" cy="260" r="10" fill="var(--gallery-ink-spot-warm)" />
    <circle cx="40" cy="35" r="7" fill="var(--gallery-ink-spot)" />
  </g>
);

export const GalleryBackground = ({ variant = 'section' }: GalleryBackgroundProps) => {
  const isPanel = variant === 'panel';
  const gradientId = isPanel ? 'panelInkGradient' : 'sectionInkGradient';
  const blurId = isPanel ? 'panelInkBlur' : 'sectionInkBlur';

  if (isPanel) {
    return (
      <svg
        className="h-full w-full overflow-visible"
        viewBox="0 0 500 300"
        preserveAspectRatio="xMidYMid meet"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--gallery-ink-0)" />
            <stop offset="30%" stopColor="var(--gallery-ink-1)" />
            <stop offset="60%" stopColor="var(--gallery-ink-2)" />
            <stop offset="100%" stopColor="var(--gallery-ink-3)" />
          </linearGradient>
          <filter id={blurId} x="-35%" y="-35%" width="170%" height="170%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="16" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g transform="translate(-58 0) scale(1.4 1)" filter={`url(#${blurId})`}>
          <path d={PANEL_INK_PATH} fill={`url(#${gradientId})`} />
          {INK_SPOTS}
        </g>
      </svg>
    );
  }

  return (
    <div
      className={cn('pointer-events-none absolute h-full w-full overflow-visible')}
      style={{ inset: '-20px -30px -15px -30px', zIndex: 0 }}
      aria-hidden
    >
      <svg
        className="h-full w-full"
        viewBox="0 0 500 200"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--gallery-ink-0)" />
            <stop offset="30%" stopColor="var(--gallery-ink-1)" />
            <stop offset="60%" stopColor="var(--gallery-ink-2)" />
            <stop offset="100%" stopColor="var(--gallery-ink-3)" />
          </linearGradient>
          <filter id={blurId} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <path d={SECTION_INK_PATH} fill={`url(#${gradientId})`} filter={`url(#${blurId})`} />
        <ellipse cx="470" cy="50" rx="18" ry="12" fill="var(--gallery-ink-spot)" />
        <ellipse cx="25" cy="160" rx="15" ry="10" fill="var(--gallery-ink-spot-warm)" />
        <circle cx="480" cy="130" r="12" fill="var(--gallery-ink-spot)" />
      </svg>
    </div>
  );
};
