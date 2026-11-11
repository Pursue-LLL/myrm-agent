import type { ReactNode } from 'react';
import { Label } from '@/components/primitives/label';

/** One labelled control of the voice form: stacked on phones, label left and control right from `sm` up. */
export function VoiceFieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <Label className="text-sm font-medium text-foreground shrink-0">{label}</Label>
      <div className="w-full sm:w-64">{children}</div>
    </div>
  );
}
