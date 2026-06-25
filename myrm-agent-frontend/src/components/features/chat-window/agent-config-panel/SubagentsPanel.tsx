'use client';

import { useState } from 'react';
import { Plus, Trash2, AlertCircle } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils/classnameUtils';
import { type AgentThemeColor, AGENT_COLOR_CLASSES } from '@/components/features/message-box/progress-steps/toolIcons';
import SubagentEntitlementGate from '@/components/billing/SubagentEntitlementGate';

type SubagentControlScope = 'leaf' | 'orchestrator';

type EphemeralSubagentConfig = {
  display_name?: string;
  theme_color?: AgentThemeColor;
  control_scope?: SubagentControlScope;
};

const AVAILABLE_COLORS: AgentThemeColor[] = ['blue', 'green', 'purple', 'orange', 'pink', 'cyan', 'amber', 'red'];

const COLOR_HEX: Record<string, string> = {
  blue: '#3b82f6',
  green: '#10b981',
  purple: '#a855f7',
  orange: '#f97316',
  pink: '#ec4899',
  cyan: '#06b6d4',
  amber: '#f59e0b',
  red: '#ef4444',
};

export interface SubagentsPanelProps {
  localEphemeralSubagents: Record<string, EphemeralSubagentConfig>;
  setLocalEphemeralSubagents: React.Dispatch<React.SetStateAction<Record<string, EphemeralSubagentConfig>>>;
  t: (key: string) => string;
  tCommon: (key: string) => string;
  displayNameErrors: Record<string, string>;
  setDisplayNameErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

export const SubagentsPanel = ({
  localEphemeralSubagents,
  setLocalEphemeralSubagents,
  t,
  tCommon,
  displayNameErrors,
  setDisplayNameErrors,
}: SubagentsPanelProps) => {
  const [isAddingSubagent, setIsAddingSubagent] = useState(false);
  const [newSubagentId, setNewSubagentId] = useState('');
  const [newSubagentIdError, setNewSubagentIdError] = useState('');
  const [selectedPreset, setSelectedPreset] = useState('');
  const [subagentToDelete, setSubagentToDelete] = useState<string | null>(null);

  const SUBAGENT_PRESETS: Record<string, EphemeralSubagentConfig & { display_name: string; theme_color: AgentThemeColor }> = {
    researcher: { display_name: t('presetResearcher'), theme_color: 'blue', control_scope: 'leaf' },
    coder: { display_name: t('presetCoder'), theme_color: 'green', control_scope: 'leaf' },
    reviewer: { display_name: t('presetReviewer'), theme_color: 'purple', control_scope: 'leaf' },
    analyst: { display_name: t('presetAnalyst'), theme_color: 'orange', control_scope: 'leaf' },
  };

  const validateSubagentId = (id: string): string => {
    if (!id) return t('errorIdRequired');
    if (id.length < 2) return t('errorIdTooShort');
    if (id.length > 50) return t('errorIdTooLong');
    if (!/^[a-z0-9_-]+$/.test(id)) return t('errorIdInvalid');
    if (localEphemeralSubagents[id]) return t('errorIdDuplicate');
    return '';
  };

  const validateDisplayName = (name: string): string => {
    if (name.length > 100) return t('errorDisplayNameTooLong');
    return '';
  };

  const handleAddSubagent = () => {
    let idToAdd = newSubagentId;
    if (selectedPreset && selectedPreset !== 'custom') {
      idToAdd = selectedPreset;
    }
    const error = validateSubagentId(idToAdd);
    if (error) {
      setNewSubagentIdError(error);
      return;
    }
    const preset = SUBAGENT_PRESETS[idToAdd];
    const newConfig: EphemeralSubagentConfig = preset
      ? { display_name: preset.display_name, theme_color: preset.theme_color, control_scope: preset.control_scope }
      : { display_name: '', theme_color: 'blue', control_scope: 'leaf' };

    setLocalEphemeralSubagents((prev) => ({ ...prev, [idToAdd]: newConfig }));
    setIsAddingSubagent(false);
    setNewSubagentId('');
    setNewSubagentIdError('');
    setSelectedPreset('');
  };

  const handleDeleteSubagent = (key: string) => {
    setLocalEphemeralSubagents((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setSubagentToDelete(null);
  };

  const handleDisplayNameChange = (key: string, name: string) => {
    const error = validateDisplayName(name);
    setDisplayNameErrors((prev) => ({ ...prev, [key]: error }));
    setLocalEphemeralSubagents((prev) => ({
      ...prev,
      [key]: { ...prev[key], display_name: name },
    }));
  };

  const handleThemeColorChange = (key: string, color: AgentThemeColor) => {
    setLocalEphemeralSubagents((prev) => ({
      ...prev,
      [key]: { ...prev[key], theme_color: color },
    }));
  };

  const handleControlScopeChange = (key: string, scope: SubagentControlScope) => {
    setLocalEphemeralSubagents((prev) => ({
      ...prev,
      [key]: { ...prev[key], control_scope: scope },
    }));
  };

  const subagentEntries = Object.entries(localEphemeralSubagents);
  const hasValidationErrors = Object.values(displayNameErrors).some((e) => e !== '');

  return (
    <SubagentEntitlementGate>
      <div className="space-y-4">
        <Button onClick={() => setIsAddingSubagent(true)} variant="outline" className="w-full gap-2 border-dashed">
          <Plus size={16} />
          {t('addSubagent')}
        </Button>

        {subagentEntries.length > 0 ? (
          <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
            {subagentEntries.map(([key, config]) => (
              <SubagentCard
                key={key}
                subagentKey={key}
                config={config}
                displayNameError={displayNameErrors[key]}
                onDisplayNameChange={handleDisplayNameChange}
                onThemeColorChange={handleThemeColorChange}
                onControlScopeChange={handleControlScopeChange}
                onDelete={() => setSubagentToDelete(key)}
                t={t}
              />
            ))}
          </div>
        ) : (
          <div className="py-8 text-center">
            <p className="text-sm text-muted-foreground mb-2">{t('noSubagents')}</p>
            <p className="text-xs text-muted-foreground/70">{t('noSubagentsDesc')}</p>
          </div>
        )}

        {/* Add subagent dialog */}
        <Dialog open={isAddingSubagent} onOpenChange={setIsAddingSubagent}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{t('addSubagent')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>{t('selectPreset')}</Label>
                <Select
                  value={selectedPreset}
                  onValueChange={(value) => {
                    setSelectedPreset(value);
                    if (value !== 'custom') {
                      setNewSubagentId(value);
                      setNewSubagentIdError('');
                    } else {
                      setNewSubagentId('');
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('selectPreset')} />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.keys(SUBAGENT_PRESETS).map((preset) => (
                      <SelectItem key={preset} value={preset}>
                        {SUBAGENT_PRESETS[preset].display_name}
                      </SelectItem>
                    ))}
                    <SelectItem value="custom">{t('customId')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {(selectedPreset === 'custom' || !selectedPreset) && (
                <div className="space-y-2">
                  <Label htmlFor="new-subagent-id">{t('subagentIdLabel')}</Label>
                  <Input
                    id="new-subagent-id"
                    value={newSubagentId}
                    onChange={(e) => {
                      setNewSubagentId(e.target.value);
                      setNewSubagentIdError('');
                    }}
                    placeholder={t('subagentIdPlaceholder')}
                    className={cn(newSubagentIdError && 'border-destructive focus-visible:ring-destructive')}
                  />
                  {newSubagentIdError && (
                    <div className="flex items-center gap-1.5 text-xs text-destructive">
                      <AlertCircle size={12} />
                      {newSubagentIdError}
                    </div>
                  )}
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsAddingSubagent(false)}>
                {tCommon('cancel')}
              </Button>
              <Button onClick={handleAddSubagent}>{tCommon('confirm')}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete confirmation dialog */}
        <Dialog open={!!subagentToDelete} onOpenChange={() => setSubagentToDelete(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{t('deleteSubagent')}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground py-4">{t('confirmDeleteSubagent')}</p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setSubagentToDelete(null)}>
                {tCommon('cancel')}
              </Button>
              <Button
                variant="destructive"
                onClick={() => subagentToDelete && handleDeleteSubagent(subagentToDelete)}
              >
                {tCommon('confirm')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {hasValidationErrors && (
          <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30 flex items-start gap-2">
            <AlertCircle size={16} className="text-destructive mt-0.5 shrink-0" />
            <p className="text-sm text-destructive">{t('fixValidationErrors')}</p>
          </div>
        )}
      </div>
    </SubagentEntitlementGate>
  );
};

function SubagentCard({
  subagentKey,
  config,
  displayNameError,
  onDisplayNameChange,
  onThemeColorChange,
  onControlScopeChange,
  onDelete,
  t,
}: {
  subagentKey: string;
  config: EphemeralSubagentConfig;
  displayNameError?: string;
  onDisplayNameChange: (key: string, name: string) => void;
  onThemeColorChange: (key: string, color: AgentThemeColor) => void;
  onControlScopeChange: (key: string, scope: SubagentControlScope) => void;
  onDelete: () => void;
  t: (key: string) => string;
}) {
  const themeColor = (config.theme_color || 'blue') as AgentThemeColor;

  return (
    <div className="p-4 rounded-lg border border-border/50 bg-muted/30 space-y-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium text-foreground">{subagentKey}</div>
        <Button
          onClick={onDelete}
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10"
        >
          <Trash2 size={14} />
        </Button>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`display-name-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentDisplayName')}
        </Label>
        <Input
          id={`display-name-${subagentKey}`}
          value={config.display_name || ''}
          onChange={(e) => onDisplayNameChange(subagentKey, e.target.value)}
          placeholder={t('subagentDisplayNamePlaceholder')}
          className={cn('h-9 text-sm', displayNameError && 'border-destructive focus-visible:ring-destructive')}
        />
        {displayNameError && (
          <div className="flex items-center gap-1.5 text-xs text-destructive">
            <AlertCircle size={12} />
            {displayNameError}
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`control-scope-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentRole')}
        </Label>
        <Select
          value={config.control_scope || 'leaf'}
          onValueChange={(value) => onControlScopeChange(subagentKey, value as SubagentControlScope)}
        >
          <SelectTrigger id={`control-scope-${subagentKey}`} className="h-9 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="leaf">
              <div className="flex flex-col py-1">
                <span>{t('subagentRoleWorker')}</span>
                <span className="text-xs text-muted-foreground">{t('subagentRoleWorkerDesc')}</span>
              </div>
            </SelectItem>
            <SelectItem value="orchestrator">
              <div className="flex flex-col py-1">
                <span>{t('subagentRoleCoordinator')}</span>
                <span className="text-xs text-muted-foreground">{t('subagentRoleCoordinatorDesc')}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`theme-color-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentThemeColor')}
        </Label>
        <Select
          value={themeColor}
          onValueChange={(value) => onThemeColorChange(subagentKey, value as AgentThemeColor)}
        >
          <SelectTrigger className="h-9 text-sm">
            <SelectValue>
              <div className="flex items-center gap-2">
                <div
                  className={cn('w-4 h-4 rounded-full border-2', AGENT_COLOR_CLASSES[themeColor]?.border || AGENT_COLOR_CLASSES.blue.border)}
                  style={{ backgroundColor: COLOR_HEX[themeColor] || COLOR_HEX.blue }}
                />
                <span className="capitalize">{themeColor}</span>
              </div>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {AVAILABLE_COLORS.map((color) => (
              <SelectItem key={color} value={color}>
                <div className="flex items-center gap-2">
                  <div
                    className={cn('w-4 h-4 rounded-full border-2', AGENT_COLOR_CLASSES[color].border)}
                    style={{ backgroundColor: COLOR_HEX[color] || COLOR_HEX.blue }}
                  />
                  <span className="capitalize">{color}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
