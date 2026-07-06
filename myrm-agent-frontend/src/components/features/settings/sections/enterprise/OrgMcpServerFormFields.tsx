'use client';

import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';

interface OrgMcpServerFormFieldsProps {
  name: string;
  type: 'sse' | 'streamable_http';
  url: string;
  description: string;
  authHeader: string;
  headersConfigured?: boolean;
  onNameChange: (value: string) => void;
  onTypeChange: (value: 'sse' | 'streamable_http') => void;
  onUrlChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAuthHeaderChange: (value: string) => void;
  t: (key: string) => string;
  namePlaceholder?: string;
}

export function OrgMcpServerFormFields({
  name,
  type,
  url,
  description,
  authHeader,
  headersConfigured = false,
  onNameChange,
  onTypeChange,
  onUrlChange,
  onDescriptionChange,
  onAuthHeaderChange,
  t,
  namePlaceholder,
}: OrgMcpServerFormFieldsProps) {
  return (
    <div className="space-y-4 py-2">
      <div className="space-y-2">
        <Label>{t('mcpName')}</Label>
        <Input
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder={namePlaceholder}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('mcpType')}</Label>
        <select
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          value={type}
          onChange={(e) => onTypeChange(e.target.value as 'sse' | 'streamable_http')}
        >
          <option value="sse">SSE</option>
          <option value="streamable_http">Streamable HTTP</option>
        </select>
      </div>
      <div className="space-y-2">
        <Label>{t('mcpUrl')}</Label>
        <Input
          value={url}
          onChange={(e) => onUrlChange(e.target.value)}
          placeholder="https://mcp.example.com/sse"
        />
      </div>
      <div className="space-y-2">
        <Label>{t('mcpServerDescription')}</Label>
        <Input
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder={t('mcpServerDescriptionPlaceholder')}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('mcpAuthHeader')}</Label>
        <Input
          value={authHeader}
          onChange={(e) => onAuthHeaderChange(e.target.value)}
          placeholder={t('mcpAuthHeaderPlaceholder')}
          type="password"
          autoComplete="off"
        />
        {headersConfigured && (
          <p className="text-xs text-muted-foreground">{t('mcpAuthHeaderKeepHint')}</p>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t('mcpSleepingHint')}</p>
    </div>
  );
}
