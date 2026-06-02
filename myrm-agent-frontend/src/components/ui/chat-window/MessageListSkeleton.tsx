'use client';

const ROWS = [
  { align: 'right' as const, widths: ['75%', '55%'] },
  { align: 'left' as const, widths: ['100%', '85%', '60%'] },
  { align: 'right' as const, widths: ['65%'] },
  { align: 'left' as const, widths: ['90%', '100%', '70%'] },
] as const;

const STAGGER_MS = 80;

function SkeletonBubble({
  align,
  widths,
  baseDelay,
}: {
  align: 'left' | 'right';
  widths: readonly string[];
  baseDelay: number;
}) {
  const isRight = align === 'right';
  return (
    <div className={`flex ${isRight ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`rounded-2xl p-4 space-y-2.5 ${
          isRight ? 'max-w-[65%] md:max-w-[50%]' : 'max-w-[85%] md:max-w-[65%]'
        } bg-muted/60 border border-border/30`}
        style={{ animationDelay: `${baseDelay}ms` }}
      >
        {widths.map((w, i) => (
          <div
            key={i}
            className="h-3.5 rounded-full bg-black/[0.06] dark:bg-white/[0.06] animate-pulse"
            style={{
              width: w,
              animationDelay: `${baseDelay + i * STAGGER_MS}ms`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export default function MessageListSkeleton() {
  let delay = 0;
  return (
    <div className="flex flex-col mx-auto max-w-5xl px-4 md:px-0 pt-8 pb-40 space-y-6" aria-label="Loading messages">
      {ROWS.map((row, i) => {
        const bubbleDelay = delay;
        delay += row.widths.length * STAGGER_MS + STAGGER_MS;
        return <SkeletonBubble key={i} align={row.align} widths={row.widths} baseDelay={bubbleDelay} />;
      })}
    </div>
  );
}
