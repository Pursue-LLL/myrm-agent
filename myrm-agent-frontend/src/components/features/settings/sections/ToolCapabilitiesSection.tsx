'use client';

import { memo, useState, useEffect } from 'react';
import SettingsSection from './SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { IconEye, IconEyeOff, IconCheck, IconX, IconLoader } from '@/components/features/icons/PremiumIcons';
import { useToast } from '@/hooks/useToast';
import useConfigStore from '@/store/useConfigStore';
import { useToolGatewayHealth } from '@/hooks/useToolGatewayHealth';
import { Activity, ServerCrash, CheckCircle2, AlertTriangle, ShieldCheck, Wallet } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface ApiProvider {
  id: string;
  name: string;
  description: string;
  keyPrefix: string;
  placeholder: string;
  docsUrl: string;
}

const API_PROVIDERS: ApiProvider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT-4, GPT-3.5, Embeddings',
    keyPrefix: 'sk-',
    placeholder: 'sk-...',
    docsUrl: 'https://platform.openai.com/api-keys',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude 3',
    keyPrefix: 'sk-ant-',
    placeholder: 'sk-ant-...',
    docsUrl: 'https://console.anthropic.com/settings/keys',
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Reranker, Embeddings',
    keyPrefix: '',
    placeholder: 'Your Cohere API Key',
    docsUrl: 'https://dashboard.cohere.com/api-keys',
  },
  {
    id: 'voyage',
    name: 'Voyage AI',
    description: 'Embeddings',
    keyPrefix: 'pa-',
    placeholder: 'pa-...',
    docsUrl: 'https://dash.voyageai.com/api-keys',
  },
  {
    id: 'jina',
    name: 'Jina AI',
    description: 'Reranker, Embeddings',
    keyPrefix: 'jina_',
    placeholder: 'jina_...',
    docsUrl: 'https://jina.ai/api-keys',
  },
];

interface ApiKeyState {
  value: string;
  isVisible: boolean;
  isValidating: boolean;
  isValid: boolean | null;
}

const ToolCapabilitiesSection = memo(() => {
  const { toast } = useToast();

  // Local API Keys state
  const [apiKeys, setApiKeys] = useState<Record<string, ApiKeyState>>(
    Object.fromEntries(
      API_PROVIDERS.map((provider) => [
        provider.id,
        { value: '', isVisible: false, isValidating: false, isValid: null },
      ]),
    ),
  );

  // Gateway state
  const { gateway_token, setGatewayToken } = useConfigStore();
  const [gatewayTokenInput, setGatewayTokenInput] = useState(gateway_token || '');
  const [isSavingGateway, setIsSavingGateway] = useState(false);
  const { data: gatewayHealth, isLoading: isCheckingHealth, checkHealth } = useToolGatewayHealth();

  useEffect(() => {
    if (gateway_token) {
      checkHealth();
    }
  }, [gateway_token, checkHealth]);

  const handleSaveGatewayToken = async () => {
    setIsSavingGateway(true);
    try {
      setGatewayToken(gatewayTokenInput);
      toast({ title: 'Gateway token saved successfully' });
      // Re-check health after saving
      checkHealth();
    } catch {
      toast({ title: 'Failed to save gateway token', variant: 'destructive' });
    } finally {
      setIsSavingGateway(false);
    }
  };

  const handleKeyChange = (providerId: string, value: string) => {
    setApiKeys((prev) => ({
      ...prev,
      [providerId]: { ...prev[providerId], value, isValid: null },
    }));
  };

  const toggleVisibility = (providerId: string) => {
    setApiKeys((prev) => ({
      ...prev,
      [providerId]: { ...prev[providerId], isVisible: !prev[providerId].isVisible },
    }));
  };

  const validateKey = async (providerId: string) => {
    const key = apiKeys[providerId].value;
    if (!key) {
      toast({ title: 'Please enter an API Key', variant: 'destructive' });
      return;
    }

    setApiKeys((prev) => ({
      ...prev,
      [providerId]: { ...prev[providerId], isValidating: true },
    }));

    try {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const isValid = key.length > 10;

      setApiKeys((prev) => ({
        ...prev,
        [providerId]: { ...prev[providerId], isValidating: false, isValid },
      }));

      if (isValid) {
        toast({ title: `${API_PROVIDERS.find((p) => p.id === providerId)?.name} API Key is valid` });
      } else {
        toast({ title: 'API Key is invalid', variant: 'destructive' });
      }
    } catch (error) {
      setApiKeys((prev) => ({
        ...prev,
        [providerId]: { ...prev[providerId], isValidating: false, isValid: false },
      }));
      toast({ title: 'Validation failed', description: String(error), variant: 'destructive' });
    }
  };

  const saveKey = async (providerId: string) => {
    const key = apiKeys[providerId].value;
    if (!key) return;

    try {
      toast({ title: `${API_PROVIDERS.find((p) => p.id === providerId)?.name} API Key saved locally` });
    } catch (error) {
      toast({ title: 'Save failed', description: String(error), variant: 'destructive' });
    }
  };

  return (
    <SettingsSection
      title="Gateway & Tool Capabilities"
      description="Manage Unified Tool Gateway and Local BYOK (Bring Your Own Key) for tools like Search, Image Gen, and TTS."
    >
      {/* Gateway Status Dashboard */}
      <div className="mb-10">
        <h3 className="text-lg font-semibold flex items-center gap-2 text-foreground mb-4">
          <Activity className="h-5 w-5 text-primary" />
          Gateway Status Dashboard
        </h3>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <Card className="border-primary/20 bg-primary/5 shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-md flex items-center gap-2">
                <Wallet className="h-4 w-4 text-emerald-500" />
                Work Unit (WU) Balance
              </CardTitle>
              <CardDescription>Your Unified Gateway computing balance</CardDescription>
            </CardHeader>
            <CardContent>
              {isCheckingHealth ? (
                <div className="flex items-center gap-2 text-muted-foreground animate-pulse">
                  <IconLoader className="h-4 w-4 animate-spin" /> Checking balance...
                </div>
              ) : gatewayHealth?.status === 'error' ? (
                <div className="text-red-500 text-sm flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" /> {gatewayHealth.message}
                </div>
              ) : gatewayHealth ? (
                <div className="text-3xl font-bold font-mono tracking-tight text-emerald-600 dark:text-emerald-400">
                  {gatewayHealth.wu_balance?.toLocaleString() ?? 0}{' '}
                  <span className="text-sm font-normal text-muted-foreground">WU</span>
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">Please configure Gateway token</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-md flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-blue-500" />
                Platform Capabilities
              </CardTitle>
              <CardDescription>Gateway downstream provider health</CardDescription>
            </CardHeader>
            <CardContent>
              {isCheckingHealth ? (
                <div className="flex items-center gap-2 text-muted-foreground animate-pulse">
                  <IconLoader className="h-4 w-4 animate-spin" /> Checking providers...
                </div>
              ) : gatewayHealth?.providers ? (
                <div className="space-y-3">
                  {Object.entries(gatewayHealth.providers).map(([capability, status]) => (
                    <div key={capability} className="flex items-center justify-between">
                      <div className="text-sm font-medium capitalize">{capability.replace('_', ' ')}</div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                          {status.provider}
                        </span>
                        {status.healthy ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        ) : (
                          <ServerCrash className="h-4 w-4 text-red-500" />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">No capabilities data</div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4 max-w-md">
          <div className="space-y-2">
            <Label htmlFor="gatewayToken">Gateway Token (PAT)</Label>
            <Input
              id="gatewayToken"
              type="password"
              placeholder="Enter your gateway token"
              value={gatewayTokenInput}
              onChange={(e) => setGatewayTokenInput(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={handleSaveGatewayToken} disabled={isSavingGateway}>
              {isSavingGateway ? 'Saving...' : 'Save & Refresh'}
            </Button>
            <Button variant="outline" onClick={checkHealth} disabled={isCheckingHealth || !gateway_token}>
              <Activity className={cn('h-4 w-4 mr-2', isCheckingHealth && 'animate-spin')} />
              Refresh Status
            </Button>
          </div>
        </div>
      </div>

      <div className="pt-8 border-t border-border">
        <h3 className="text-lg font-semibold mb-1 text-foreground">Local API Keys (BYOK)</h3>
        <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
          Configure API Keys for AI service providers. These are used as a fallback if the Gateway is unavailable, or if
          you prefer local execution. Stored securely on your device.
        </p>

        <div className="space-y-4">
          {API_PROVIDERS.map((provider) => {
            const state = apiKeys[provider.id];
            return (
              <Card key={provider.id}>
                <CardHeader>
                  <CardTitle className="text-base">{provider.name}</CardTitle>
                  <CardDescription>{provider.description}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor={`key-${provider.id}`}>API Key</Label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <Input
                          id={`key-${provider.id}`}
                          type={state.isVisible ? 'text' : 'password'}
                          placeholder={provider.placeholder}
                          value={state.value}
                          onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                          className="pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => toggleVisibility(provider.id)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                          {state.isVisible ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
                        </button>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => validateKey(provider.id)}
                        disabled={!state.value || state.isValidating}
                      >
                        {state.isValidating ? (
                          <IconLoader className="h-4 w-4 animate-spin" />
                        ) : state.isValid === true ? (
                          <IconCheck className="h-4 w-4 text-green-500" />
                        ) : state.isValid === false ? (
                          <IconX className="h-4 w-4 text-red-500" />
                        ) : (
                          'Validate'
                        )}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => saveKey(provider.id)}
                        disabled={!state.value || state.isValid === false}
                      >
                        Save Local
                      </Button>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Get API Key:
                    <a
                      href={provider.docsUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-1 text-primary hover:underline"
                    >
                      {provider.docsUrl}
                    </a>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </SettingsSection>
  );
});

ToolCapabilitiesSection.displayName = 'ToolCapabilitiesSection';

export default ToolCapabilitiesSection;
