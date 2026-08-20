'use client';

import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';

export type OrgMcpType = 'sse' | 'streamable_http' | 'tunnel';

interface OrgMcpServerFormFieldsProps {
  name: string;
  type: OrgMcpType;
  url: string;
  description: string;
  authHeader: string;
  tunnelId: string;
  aclGroups: string;
  headersConfigured?: boolean;
  tunnels?: { id: string; name: string; status: string }[];
  onNameChange: (value: string) => void;
  onTypeChange: (value: OrgMcpType) => void;
  onUrlChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAuthHeaderChange: (value: string) => void;
  onTunnelIdChange: (value: string) => void;
  onAclGroupsChange: (value: string) => void;
  t: (key: string) => string;
  namePlaceholder?: string;
}

export function OrgMcpServerFormFields({
  name,
  type,
  url,
  description,
  authHeader,
  tunnelId,
  aclGroups,
  headersConfigured = false,
  tunnels = [],
  onNameChange,
  onTypeChange,
  onUrlChange,
  onDescriptionChange,
  onAuthHeaderChange,
  onTunnelIdChange,
  onAclGroupsChange,
  t,
  namePlaceholder,
}: OrgMcpServerFormFieldsProps) {
  const isTunnel = type === 'tunnel';

  return (
    <div className="space-y-4 py-2">
      <div className="space-y-2">
        <Label>{t('mcpName')}</Label>
        <Input value={name} onChange={(e) => onNameChange(e.target.value)} placeholder={namePlaceholder} />
      </div>
      <div className="space-y-2">
        <Label>{t('mcpType')}</Label>
        <select
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          value={type}
          onChange={(e) => onTypeChange(e.target.value as OrgMcpType)}
        >
          <option value="sse">SSE</option>
          <option value="streamable_http">Streamable HTTP</option>
          <option value="tunnel">{t('mcpTypeTunnel')}</option>
        </select>
      </div>
      {isTunnel ? (
        <div className="space-y-2">
          <Label>{t('mcpTunnelSelect')}</Label>
          {tunnels.length > 0 ? (
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              value={tunnelId}
              onChange={(e) => onTunnelIdChange(e.target.value)}
            >
              <option value="">{t('mcpTunnelSelectPlaceholder')}</option>
              {tunnels.map((tun) => (
                <option key={tun.id} value={tun.id}>
                  {tun.name} ({tun.status})
                </option>
              ))}
            </select>
          ) : (
            <p className="text-xs text-muted-foreground">{t('mcpTunnelNone')}</p>
          )}
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <Label>{t('mcpUrl')}</Label>
            <Input
              value={url}
              onChange={(e) => onUrlChange(e.target.value)}
              placeholder="https://mcp.example.com/sse"
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
            {headersConfigured && <p className="text-xs text-muted-foreground">{t('mcpAuthHeaderKeepHint')}</p>}
          </div>
        </>
      )}
      <div className="space-y-2">
        <Label>{t('mcpServerDescription')}</Label>
        <Input
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          placeholder={t('mcpServerDescriptionPlaceholder')}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('mcpAclGroups')}</Label>
        <Input
          value={aclGroups}
          onChange={(e) => onAclGroupsChange(e.target.value)}
          placeholder={t('mcpAclGroupsPlaceholder')}
        />
        <p className="text-xs text-muted-foreground">{t('mcpAclGroupsHint')}</p>
      </div>
      <p className="text-xs text-muted-foreground">{t('mcpSleepingHint')}</p>
    </div>
  );
}
