'use client';

/**
 * [INPUT]
 * - @/components/primitives/input::Input, @/components/primitives/label::Label (POS: form primitives)
 *
 * [OUTPUT]
 * - TextField: a labelled single-line field, with an optional line of help below it
 *
 * [POS]
 * The one field shape of the cloud sync card. The label is bound to its input and the help to the input's description,
 * so assistive technology reads what each field is for.
 */

import { useId } from 'react';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: 'text' | 'password';
  placeholder?: string;
  autoComplete?: string;
  hint?: string;
}

export function TextField({ label, value, onChange, type = 'text', placeholder, autoComplete, hint }: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-semibold text-foreground">
        {label}
      </Label>
      <Input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        aria-describedby={hint ? hintId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && (
        <p id={hintId} className="text-xs leading-relaxed text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}
