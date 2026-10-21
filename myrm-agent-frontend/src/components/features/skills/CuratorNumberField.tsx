'use client';

import { memo, useId } from 'react';
import { Label } from '@/components/primitives/label';
import CuratorNumberInput from './CuratorNumberInput';

interface CuratorNumberFieldProps {
  label: string;
  description?: string;
  value: number;
  min: number;
  max?: number;
  step?: number;
  onCommit: (value: number) => void;
}

/** A threshold field whose label names the input and whose description is announced with it. */
const CuratorNumberField = memo(({ label, description, ...input }: CuratorNumberFieldProps) => {
  const id = useId();
  const descriptionId = `${id}-description`;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <CuratorNumberInput
        id={id}
        aria-describedby={description ? descriptionId : undefined}
        className="h-8"
        {...input}
      />
      {description && (
        <p id={descriptionId} className="text-[11px] text-muted-foreground">
          {description}
        </p>
      )}
    </div>
  );
});

CuratorNumberField.displayName = 'CuratorNumberField';

export default CuratorNumberField;
