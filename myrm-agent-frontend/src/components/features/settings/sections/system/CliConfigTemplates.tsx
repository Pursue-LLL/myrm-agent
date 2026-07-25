'use client';

import { memo, useState, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { IconCopy, IconCheck } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/useToast';

interface ToolTemplate {
  id: string;
  name: string;
  configFn: (endpoint: string, key: string) => string;
}

const TOOLS: ToolTemplate[] = [
  {
    id: 'codex',
    name: 'Codex CLI',
    configFn: (ep, key) =>
      `# Environment variables\nexport OPENAI_API_KEY=${key}\nexport OPENAI_BASE_URL=${ep}`,
  },
  {
    id: 'claude-code',
    name: 'Claude Code',
    configFn: (ep, key) =>
      `# Environment variables\nexport ANTHROPIC_BASE_URL=${ep}\nexport ANTHROPIC_API_KEY=${key}`,
  },
  {
    id: 'cursor',
    name: 'Cursor',
    configFn: (ep, key) =>
      `# Cursor Settings > Models > OpenAI API Key\n# Base URL: ${ep}\n# API Key: ${key}\n# Then select any model from your configured providers.`,
  },
  {
    id: 'aider',
    name: 'Aider',
    configFn: (ep, key) =>
      `# ~/.aider.conf.yml\nopenai-api-base: ${ep}\nopenai-api-key: ${key}\n\n# Or environment variables:\nexport OPENAI_API_BASE=${ep}\nexport OPENAI_API_KEY=${key}`,
  },
  {
    id: 'cline',
    name: 'Cline',
    configFn: (ep, key) =>
      `// VS Code Settings > Cline\n{\n  "apiProvider": "openai-compatible",\n  "apiBaseUrl": "${ep}",\n  "apiKey": "${key}"\n}`,
  },
  {
    id: 'continue',
    name: 'Continue',
    configFn: (ep, key) =>
      `# ~/.continue/config.yaml\nmodels:\n  - provider: openai\n    title: MyrmAgent\n    apiBase: ${ep}\n    apiKey: ${key}`,
  },
  {
    id: 'opencode',
    name: 'OpenCode',
    configFn: (ep, key) =>
      `// ~/.config/opencode/opencode.json\n{\n  "provider": "openai-compat",\n  "apiBase": "${ep}",\n  "apiKey": "${key}"\n}`,
  },
  {
    id: 'goose',
    name: 'Goose',
    configFn: (ep, key) =>
      `# ~/.config/goose/config.yaml\nprovider: openai\n\n# Environment variables:\nexport GOOSE_PROVIDER=openai\nexport OPENAI_API_KEY=${key}\nexport OPENAI_BASE_URL=${ep}`,
  },
  {
    id: 'qwen',
    name: 'Qwen Code',
    configFn: (ep, key) =>
      `// ~/.qwen/settings.json\n{\n  "modelProviders": {\n    "openai": {\n      "apiBase": "${ep}",\n      "apiKey": "${key}"\n    }\n  }\n}`,
  },
];

interface Props {
  apiEndpoint: string;
  apiKeyPlaceholder?: string;
}

const CliConfigTemplates = memo(({ apiEndpoint, apiKeyPlaceholder = 'sk-myrm-...' }: Props) => {
  const t = useTranslations('settings.proxy.cliConfig');
  const [activeTool, setActiveTool] = useState(TOOLS[0].id);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const activeConfig = useMemo(() => {
    const tool = TOOLS.find(item => item.id === activeTool);
    return tool?.configFn(apiEndpoint, apiKeyPlaceholder) ?? '';
  }, [activeTool, apiEndpoint, apiKeyPlaceholder]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(activeConfig);
      setCopiedId(activeTool);
      toast({ title: t('copied') });
      setTimeout(() => setCopiedId(null), 2000);
    } catch { /* clipboard not available */ }
  }, [activeConfig, activeTool, t]);

  return (
    <div className="p-4 rounded-lg border border-border/50 bg-muted/30 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">{t('title')}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('description')}</p>
        </div>
        <Button size="sm" variant="outline" onClick={handleCopy}>
          {copiedId === activeTool ? (
            <IconCheck className="h-3.5 w-3.5 mr-1 text-green-500" />
          ) : (
            <IconCopy className="h-3.5 w-3.5 mr-1" />
          )}
          {t('copy')}
        </Button>
      </div>

      <div className="flex flex-wrap gap-1">
        {TOOLS.map(tool => (
          <button
            key={tool.id}
            className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
              activeTool === tool.id
                ? 'bg-primary text-primary-foreground'
                : 'bg-background text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
            onClick={() => setActiveTool(tool.id)}
          >
            {tool.name}
          </button>
        ))}
      </div>

      <pre className="p-3 rounded bg-background text-xs font-mono overflow-x-auto whitespace-pre max-h-48">{activeConfig}</pre>
    </div>
  );
});

CliConfigTemplates.displayName = 'CliConfigTemplates';

export default CliConfigTemplates;
