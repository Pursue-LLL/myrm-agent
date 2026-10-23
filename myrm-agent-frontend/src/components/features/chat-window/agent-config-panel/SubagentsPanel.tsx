'use client';

/**
 * [INPUT]
 * - @/components/primitives::{Button, Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue}
 * - @/components/features/message-box/progress-steps/toolIcons::AgentThemeColor
 * - ./SubagentCard::{SubagentCard, EphemeralSubagentConfig, SubagentControlScope}
 *
 * [OUTPUT]
 * - SubagentsPanel: 智能体配置面板子组件，支持查看、添加、编辑和删除子代理，支持每角色模型覆盖降本
 *
 * [POS]
 * Agent 编辑面板下的 Subagent 角色集管理视图。支持为每个子代理角色配置专属经济型模型。
 */

import { useState } from 'react';
import { Plus, AlertCircle } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils/classnameUtils';
import { type AgentThemeColor } from '@/components/features/message-box/progress-steps/toolIcons';
import { SubagentCard, type EphemeralSubagentConfig, type SubagentControlScope } from './SubagentCard';

export type { EphemeralSubagentConfig, SubagentControlScope } from './SubagentCard';

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

  const SUBAGENT_PRESETS: Record<
    string,
    EphemeralSubagentConfig & { display_name: string; theme_color: AgentThemeColor }
  > = {
    researcher: {
      display_name: t('presetResearcher'),
      theme_color: 'blue',
      control_scope: 'leaf',
      model_override: 'deepseek-chat',
    },
    coder: { display_name: t('presetCoder'), theme_color: 'green', control_scope: 'leaf' },
    reviewer: {
      display_name: t('presetReviewer'),
      theme_color: 'purple',
      control_scope: 'leaf',
      model_override: 'deepseek-chat',
    },
    analyst: {
      display_name: t('presetAnalyst'),
      theme_color: 'orange',
      control_scope: 'leaf',
      model_override: 'gpt-4o-mini',
    },
  };

  const validateSubagentId = (id: string): string => {
    if (!id) {
      return t('errorIdRequired');
    }
    if (id.length < 2) {
      return t('errorIdTooShort');
    }
    if (id.length > 50) {
      return t('errorIdTooLong');
    }
    if (!/^[a-z0-9_-]+$/.test(id)) {
      return t('errorIdInvalid');
    }
    if (localEphemeralSubagents[id]) {
      return t('errorIdDuplicate');
    }
    return '';
  };

  const validateDisplayName = (name: string): string => {
    if (name.length > 100) {
      return t('errorDisplayNameTooLong');
    }
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
      ? {
          display_name: preset.display_name,
          theme_color: preset.theme_color,
          control_scope: preset.control_scope,
          model_override: preset.model_override,
        }
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

  const handleModelOverrideChange = (key: string, model: string | undefined) => {
    setLocalEphemeralSubagents((prev) => ({
      ...prev,
      [key]: { ...prev[key], model_override: model },
    }));
  };

  const subagentEntries = Object.entries(localEphemeralSubagents);
  const hasValidationErrors = Object.values(displayNameErrors).some((e) => e !== '');

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('builtinSpecialistsHint')}</p>
      <Button
        onClick={() => setIsAddingSubagent(true)}
        variant="outline"
        className="w-full gap-2 border-dashed cursor-pointer"
      >
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
              onModelOverrideChange={handleModelOverrideChange}
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
            <Button variant="destructive" onClick={() => subagentToDelete && handleDeleteSubagent(subagentToDelete)}>
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
  );
};

export default SubagentsPanel;
