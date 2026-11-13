import type { ReactNode } from 'react';
import { Label } from '@/components/primitives/label';

interface VoiceFieldRowProps {
  label: string;
  /** Id of the control in `children`: it is what names that control for assistive technology. */
  htmlFor: string;
  children: ReactNode;
}

/** One labelled control of the voice form: stacked on phones, label left and control right from `sm` up. */
export function VoiceFieldRow({ label, htmlFor, children }: VoiceFieldRowProps) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <Label htmlFor={htmlFor} className="text-sm font-medium text-foreground shrink-0">
        {label}
      </Label>
      <div className="w-full sm:w-64">{children}</div>
    </div>
  );
}
