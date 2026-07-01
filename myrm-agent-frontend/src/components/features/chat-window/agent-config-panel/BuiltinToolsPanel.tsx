'use client';

import {
  Globe,
  Cable,
  Monitor,
  Image,
  Video,
  Search,
  FolderOpen,
  TerminalSquare,
  BrainCircuit,
  BookMarked,
  KanbanSquare,
  PenTool,
  Volume2,
  LayoutTemplate,
  MessageSquareCheck,
  AlertCircle,
  ListTodo,
} from 'lucide-react';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { BUILTIN_TOOL_IDS, type BuiltinToolId } from '@/store/chat/types';
import { SelectableCard } from './AgentConfigSelectableCard';
import { CuPermissionInline } from './CuPermissionInline';

export interface BuiltinToolsPanelProps {
  localBuiltinTools: BuiltinToolId[];
  setLocalBuiltinTools: React.Dispatch<React.SetStateAction<BuiltinToolId[]>>;
  localAutoRestoreDomains: string[];
  setLocalAutoRestoreDomains: React.Dispatch<React.SetStateAction<string[]>>;
  localBrowserEngine?: string;
  setLocalBrowserEngine: React.Dispatch<React.SetStateAction<string | undefined>>;
  localBrowserSource?: string;
  setLocalBrowserSource: React.Dispatch<React.SetStateAction<string | undefined>>;
  localDialogPolicy?: string;
  setLocalDialogPolicy: React.Dispatch<React.SetStateAction<string | undefined>>;
  localSessionRecording?: string;
  setLocalSessionRecording: React.Dispatch<React.SetStateAction<string | undefined>>;
  t: (key: string) => string;
  tAgent: (key: string) => string;
  tPanel: (key: string) => string;
}

const BUILTIN_TOOL_ICONS: Record<BuiltinToolId, React.ReactNode> = {
  web_search: <Globe size={14} />,
  memory: <BrainCircuit size={14} />,
  file_ops: <FolderOpen size={14} />,
  code_execute: <TerminalSquare size={14} />,
  wiki: <BookMarked size={14} />,
  browser: <Monitor size={14} />,
  computer_use: <Monitor size={14} />,
  image_generation: <Image size={14} />,
  video_generation: <Video size={14} />,
  tts: <Volume2 size={14} />,
  kanban: <KanbanSquare size={14} />,
  canvas: <PenTool size={14} />,
  answer_tool: <MessageSquareCheck size={14} />,
  render_ui: <LayoutTemplate size={14} />,
  planning: <ListTodo size={14} />,
};

export const BuiltinToolsPanel = ({
  localBuiltinTools,
  setLocalBuiltinTools,
  localAutoRestoreDomains,
  setLocalAutoRestoreDomains,
  localBrowserEngine,
  setLocalBrowserEngine,
  localBrowserSource,
  setLocalBrowserSource,
  localDialogPolicy,
  setLocalDialogPolicy,
  localSessionRecording,
  setLocalSessionRecording,
  t,
  tAgent,
  tPanel,
}: BuiltinToolsPanelProps) => {
  const toggleBuiltinTool = (id: BuiltinToolId) => {
    setLocalBuiltinTools((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {BUILTIN_TOOL_IDS.map((id) => (
          <SelectableCard
            key={id}
            id={`builtin-${id}`}
            label={tPanel(`builtinToolNames.${id}`)}
            description={tPanel(`builtinToolDescs.${id}`)}
            checked={localBuiltinTools.includes(id)}
            onCheckedChange={() => toggleBuiltinTool(id)}
            icon={BUILTIN_TOOL_ICONS[id]}
            colorClass="text-orange-500"
          />
        ))}
      </div>

      {localBuiltinTools.includes('browser') && (
        <BrowserConfigSection
          localAutoRestoreDomains={localAutoRestoreDomains}
          setLocalAutoRestoreDomains={setLocalAutoRestoreDomains}
          localBrowserEngine={localBrowserEngine}
          setLocalBrowserEngine={setLocalBrowserEngine}
          localBrowserSource={localBrowserSource}
          setLocalBrowserSource={setLocalBrowserSource}
          localDialogPolicy={localDialogPolicy}
          setLocalDialogPolicy={setLocalDialogPolicy}
          localSessionRecording={localSessionRecording}
          setLocalSessionRecording={setLocalSessionRecording}
          t={t}
          tAgent={tAgent}
          tPanel={tPanel}
        />
      )}

      {localBuiltinTools.includes('computer_use') && <CuPermissionInline tPanel={tPanel} />}
    </div>
  );
};

function BrowserConfigSection({
  localAutoRestoreDomains,
  setLocalAutoRestoreDomains,
  localBrowserEngine,
  setLocalBrowserEngine,
  localBrowserSource,
  setLocalBrowserSource,
  localDialogPolicy,
  setLocalDialogPolicy,
  localSessionRecording,
  setLocalSessionRecording,
  t,
  tAgent,
  tPanel,
}: Omit<BuiltinToolsPanelProps, 'localBuiltinTools' | 'setLocalBuiltinTools'>) {
  return (
    <div className="space-y-4 p-3 rounded-xl bg-muted/30 border border-border/50">
      {/* Auto-restore domains */}
      <div className="space-y-2">
        <Label className="text-sm font-medium flex items-center gap-2">
          <Monitor size={14} className="text-blue-500" />
          {tPanel('autoRestoreDomains')}
        </Label>
        <p className="text-xs text-muted-foreground">{tPanel('autoRestoreDomainsDesc')}</p>
        <Input
          value={localAutoRestoreDomains.join(', ')}
          onChange={(e) => {
            const val = e.target.value;
            if (!val.trim()) {
              setLocalAutoRestoreDomains([]);
            } else {
              setLocalAutoRestoreDomains(
                val
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              );
            }
          }}
          placeholder="github.com, twitter.com"
          className="bg-background"
        />
      </div>

      {/* Browser Engine */}
      <div className="space-y-2 pt-2 border-t border-border/50">
        <Label className="text-sm font-medium flex items-center gap-2">
          <Globe size={14} className="text-blue-500" />
          {tAgent('browserEngine.label')}
        </Label>
        <p className="text-xs text-muted-foreground">{tAgent('browserEngine.description')}</p>
        <Select
          value={localBrowserEngine || 'chromium_patchright'}
          onValueChange={(value) => setLocalBrowserEngine(value === 'chromium_patchright' ? undefined : value)}
        >
          <SelectTrigger className="w-full bg-background">
            <SelectValue placeholder={tAgent('browserEngine.label')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="chromium_patchright">
              <div className="flex flex-col py-1">
                <span className="font-medium">{tAgent('browserEngine.chromium')}</span>
                <span className="text-xs text-muted-foreground">{tAgent('browserEngine.chromiumDesc')}</span>
              </div>
            </SelectItem>
            <SelectItem value="firefox_camoufox">
              <div className="flex flex-col py-1">
                <span className="font-medium">{tAgent('browserEngine.camoufox')}</span>
                <span className="text-xs text-muted-foreground">{tAgent('browserEngine.camoufoxDesc')}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Browser Source */}
      <div className="space-y-2 pt-2 border-t border-border/50">
        <Label className="text-sm font-medium flex items-center gap-2">
          <Cable size={14} className="text-green-500" />
          {t('browserSource.label')}
        </Label>
        <p className="text-xs text-muted-foreground">{t('browserSource.description')}</p>
        <Select
          value={localBrowserSource || 'auto'}
          onValueChange={(value) => setLocalBrowserSource(value === 'auto' ? undefined : value)}
        >
          <SelectTrigger className="w-full bg-background">
            <SelectValue placeholder={t('browserSource.placeholder')} />
          </SelectTrigger>
          <SelectContent>
            {(['auto', 'extension', 'launch', 'connect', 'remote'] as const).map((opt) => (
              <SelectItem key={opt} value={opt}>
                <div className="flex flex-col py-1">
                  <span className="font-medium">{t(`browserSource.options.${opt}`)}</span>
                  <span className="text-xs text-muted-foreground">{t(`browserSource.options.${opt}Desc`)}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {localBrowserSource === 'extension' && (
          <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
            <AlertCircle size={12} />
            {t('browserSource.extensionWarning')}
          </p>
        )}
        {localBrowserSource === 'connect' && (
          <p className="text-xs text-blue-600 dark:text-blue-400 flex items-center gap-1">
            <AlertCircle size={12} />
            {t('browserSource.connectInfo')}
          </p>
        )}
        {localBrowserSource === 'remote' && (
          <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
            <AlertCircle size={12} />
            {t('browserSource.remoteWarning')}
          </p>
        )}
      </div>

      {/* Dialog Policy */}
      <div className="space-y-2 pt-2 border-t border-border/50">
        <Label className="text-sm font-medium flex items-center gap-2">{t('dialogPolicy.label')}</Label>
        <p className="text-xs text-muted-foreground">{t('dialogPolicy.description')}</p>
        <Select
          value={localDialogPolicy || 'smart'}
          onValueChange={(value) => setLocalDialogPolicy(value === 'smart' ? undefined : value)}
        >
          <SelectTrigger className="w-full bg-background">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(['smart', 'auto_accept', 'auto_dismiss', 'wait_for_agent'] as const).map((opt) => (
              <SelectItem key={opt} value={opt}>
                <div className="flex flex-col py-1">
                  <span className="font-medium">
                    {t(`dialogPolicy.options.${opt === 'auto_accept' ? 'autoAccept' : opt === 'auto_dismiss' ? 'autoDismiss' : opt === 'wait_for_agent' ? 'waitForAgent' : opt}`)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t(`dialogPolicy.options.${opt === 'auto_accept' ? 'autoAccept' : opt === 'auto_dismiss' ? 'autoDismiss' : opt === 'wait_for_agent' ? 'waitForAgent' : opt}Desc`)}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Session Recording */}
      <div className="space-y-2 pt-2 border-t border-border/50">
        <Label className="text-sm font-medium flex items-center gap-2">{t('sessionRecording.label')}</Label>
        <p className="text-xs text-muted-foreground">{t('sessionRecording.description')}</p>
        <Select
          value={localSessionRecording || 'off'}
          onValueChange={(value) => setLocalSessionRecording(value === 'off' ? undefined : value)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(['off', 'on_failure', 'always'] as const).map((opt) => (
              <SelectItem key={opt} value={opt}>
                <div className="flex flex-col py-1">
                  <span className="font-medium">
                    {t(`sessionRecording.options.${opt === 'on_failure' ? 'onFailure' : opt}`)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t(`sessionRecording.options.${opt === 'on_failure' ? 'onFailure' : opt}Desc`)}
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
