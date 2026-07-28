'use client';

export function EmbedFail({ label }: { label: string }) {
  return (
    <span className="flex size-full items-center justify-center rounded-lg border border-dashed border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive/70">
      Failed to load {label} embed
    </span>
  );
}
