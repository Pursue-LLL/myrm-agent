/**
 * [INPUT]
 * - None (pure TypeScript definitions)
 *
 * [OUTPUT]
 * - UIRequestType, UISelectOption, UIRequestItem, UIResponsePayload
 *
 * [POS]
 * Client-side data contracts for Transport-Agnostic Extension UI Sub-Protocol (Item 28).
 * Strictly typed, zero `any`, file length < 80 lines.
 */

export type UIRequestType = 'select' | 'confirm' | 'input' | 'editor' | 'notify';

export interface UISelectOption {
  label: string;
  value: string;
  description?: string | null;
}

export interface UIRequestItem {
  request_id: string;
  request_type: UIRequestType;
  title: string;
  message?: string | null;
  options?: UISelectOption[] | null;
  placeholder?: string | null;
  default_value?: string | boolean | null;
  content?: string | null;
  language?: string | null;
  timeout_s?: number;
  created_at?: number;
}

export interface UIResponsePayload {
  value?: string | boolean | null;
  cancelled?: boolean;
  error?: string | null;
}
