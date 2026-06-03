'use client';

/**
 * Skill Instance Manager Component
 *
 * Provides UI for managing skill instances (multi-instance support).
 * Users can create, edit, and delete skill instances with different configurations.
 *
 * Design:
 * - List all instances for a skill
 * - Create new instance with env/config overrides
 * - Edit existing instance
 * - Delete instance
 * - Instance selection for skill execution
 */

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Edit, Trash2, Settings } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { toast } from '@/hooks/useToast';
import { KeyValueEditor } from '@/components/features/app-shell/key-value-editor';
import { JsonEditor } from '@/components/features/app-shell/json-editor';
import { SchemaForm } from '@/components/features/app-shell/schema-form';

interface ConfigPropertySchema {
  type?: string;
  title?: string;
  description?: string;
  default?: string | number | boolean | null;
  enum?: (string | number | boolean | null)[];
  format?: string;
  minimum?: number;
  maximum?: number;
}

interface ConfigSchema {
  type?: string;
  properties?: Record<string, ConfigPropertySchema>;
  required?: string[];
}

interface SkillInstance {
  instance_name: string;
  skill_name: string;
  created_at: string;
  updated_at: string;
  env_overrides: Record<string, string>;
  config_overrides: Record<string, unknown>;
  state_file: string | null;
  config_schema?: ConfigSchema | null;
  is_default?: boolean;
}

interface SkillInstanceManagerProps {
  skillName: string;
  onClose?: () => void;
}

export const SkillInstanceManager = memo<SkillInstanceManagerProps>(({ skillName, onClose: _onClose }) => {
  const t = useTranslations('settings.skills.instances');

  const [instances, setInstances] = useState<string[]>([]);
  const [defaultInstance, setDefaultInstance] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedInstance, setSelectedInstance] = useState<SkillInstance | null>(null);

  // Form state
  const [instanceName, setInstanceName] = useState('');
  const [envOverrides, setEnvOverrides] = useState<Record<string, string>>({});
  const [configOverrides, setConfigOverrides] = useState<Record<string, unknown>>({});
  const [configSchema, setConfigSchema] = useState<ConfigSchema | null>(null);

  // Load default instance from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(`skill-default-instance-${skillName}`);
    if (stored) {
      setDefaultInstance(stored);
    }
  }, [skillName]);

  // Set default instance
  const handleSetDefault = useCallback(
    (instanceName: string) => {
      localStorage.setItem(`skill-default-instance-${skillName}`, instanceName);
      setDefaultInstance(instanceName);

      // Emit custom event for Agent layer to reload config
      window.dispatchEvent(
        new CustomEvent('skill-instance-changed', {
          detail: { skillName, instanceName },
        }),
      );

      toast({
        title: t('defaultSet'),
        description: t('defaultSetDescription', { name: instanceName }),
      });
    },
    [skillName, t],
  );

  // Fetch skill schema (once on mount)
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/api/v1/skills/${skillName}`);
        if (res.ok) {
          const data = await res.json();
          if (data.config_schema) {
            setConfigSchema(data.config_schema);
          }
        }
      } catch {
        // Schema fetch is best-effort; fallback to JsonEditor
      }
    })();
  }, [skillName]);

  // Fetch instances list
  const fetchInstances = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/v1/skills/${skillName}/instances`);
      if (!response.ok) {
        throw new Error('Failed to fetch instances');
      }
      const data = await response.json();
      setInstances(data.instances || []);
    } catch (error) {
      toast({
        title: t('fetchError'),
        description: String(error),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [skillName, t]);

  useEffect(() => {
    fetchInstances();
  }, [fetchInstances]);

  // Create instance
  const handleCreate = useCallback(async () => {
    if (!instanceName.trim()) {
      toast({
        title: t('createError'),
        description: t('instanceNameRequired'),
        variant: 'destructive',
      });
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/v1/skills/${skillName}/instances`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instance_name: instanceName,
          env_overrides: envOverrides,
          config_overrides: configOverrides,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create instance');
      }

      toast({
        title: t('createSuccess'),
        description: t('instanceCreated', { name: instanceName }),
      });

      setCreateDialogOpen(false);
      setInstanceName('');
      setEnvOverrides({});
      setConfigOverrides({});
      fetchInstances();
    } catch (error) {
      toast({
        title: t('createError'),
        description: String(error),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [skillName, instanceName, envOverrides, configOverrides, t, fetchInstances]);

  // Update instance
  const handleUpdate = useCallback(async () => {
    if (!selectedInstance) return;

    setLoading(true);
    try {
      const response = await fetch(`/api/v1/skills/${skillName}/instances/${selectedInstance.instance_name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          env_overrides: envOverrides,
          config_overrides: configOverrides,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to update instance');
      }

      toast({
        title: t('updateSuccess'),
        description: t('instanceUpdated', { name: selectedInstance.instance_name }),
      });

      setEditDialogOpen(false);
      setSelectedInstance(null);
      setEnvOverrides({});
      setConfigOverrides({});
      fetchInstances();
    } catch (error) {
      toast({
        title: t('updateError'),
        description: String(error),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [skillName, selectedInstance, envOverrides, configOverrides, t, fetchInstances]);

  // Delete instance
  const handleDelete = useCallback(async () => {
    if (!selectedInstance) return;

    setLoading(true);
    try {
      const response = await fetch(`/api/v1/skills/${skillName}/instances/${selectedInstance.instance_name}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete instance');
      }

      toast({
        title: t('deleteSuccess'),
        description: t('instanceDeleted', { name: selectedInstance.instance_name }),
      });

      setDeleteDialogOpen(false);
      setSelectedInstance(null);
      fetchInstances();
    } catch (error) {
      toast({
        title: t('deleteError'),
        description: String(error),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [skillName, selectedInstance, t, fetchInstances]);

  // Open edit dialog
  const handleEditClick = useCallback(
    async (instanceName: string) => {
      setLoading(true);
      try {
        const response = await fetch(`/api/v1/skills/${skillName}/instances/${instanceName}`);
        if (!response.ok) {
          throw new Error('Failed to fetch instance details');
        }
        const data: SkillInstance = await response.json();
        setSelectedInstance(data);
        setEnvOverrides(data.env_overrides || {});
        setConfigOverrides(data.config_overrides || {});
        setConfigSchema(data.config_schema ?? null);
        setEditDialogOpen(true);
      } catch (error) {
        toast({
          title: t('fetchError'),
          description: String(error),
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    },
    [skillName, t],
  );

  // Open delete dialog
  const handleDeleteClick = useCallback(
    async (instanceName: string) => {
      setLoading(true);
      try {
        const response = await fetch(`/api/v1/skills/${skillName}/instances/${instanceName}`);
        if (!response.ok) {
          throw new Error('Failed to fetch instance details');
        }
        const data: SkillInstance = await response.json();
        setSelectedInstance(data);
        setDeleteDialogOpen(true);
      } catch (error) {
        toast({
          title: t('fetchError'),
          description: String(error),
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    },
    [skillName, t],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">{t('title')}</h3>
          <p className="text-sm text-muted-foreground">{t('description', { skill: skillName })}</p>
        </div>
        <Button
          onClick={() => {
            setInstanceName('');
            setEnvOverrides({});
            setConfigOverrides({});
            setCreateDialogOpen(true);
          }}
          size="sm"
        >
          <Plus className="mr-2 h-4 w-4" />
          {t('createInstance')}
        </Button>
      </div>

      {/* Instances list */}
      <div className="space-y-2">
        {loading && instances.length === 0 ? (
          <div className="text-center text-sm text-muted-foreground py-8">{t('loading')}</div>
        ) : instances.length === 0 ? (
          <div className="text-center text-sm text-muted-foreground py-8">{t('noInstances')}</div>
        ) : (
          instances.map((name) => (
            <div
              key={name}
              className={cn(
                'flex items-center justify-between p-3 rounded-lg border',
                'hover:bg-accent/50 transition-colors',
                defaultInstance === name && 'border-primary bg-primary/5',
              )}
            >
              <div className="flex items-center gap-2">
                <Settings className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{name}</span>
                {defaultInstance === name ? (
                  <Badge variant="default" className="text-xs">
                    {t('default')}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs">
                    {t('instance')}
                  </Badge>
                )}
              </div>
              <div className="flex gap-2">
                {defaultInstance !== name && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleSetDefault(name)}
                    disabled={loading}
                    title={t('setAsDefault')}
                  >
                    {t('setDefault')}
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => handleEditClick(name)} disabled={loading}>
                  <Edit className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleDeleteClick(name)} disabled={loading}>
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('createDialogTitle')}</DialogTitle>
            <DialogDescription>{t('createDialogDescription', { skill: skillName })}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="instance-name">{t('instanceName')}</Label>
              <Input
                id="instance-name"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                placeholder={t('instanceNamePlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('envOverrides')}</Label>
              <p className="text-xs text-muted-foreground">{t('envOverridesDescription')}</p>
              <KeyValueEditor
                value={envOverrides}
                onChange={setEnvOverrides}
                keyPlaceholder="ENV_VAR_NAME"
                valuePlaceholder="value"
                valueType="password"
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('configOverrides')}</Label>
              <p className="text-xs text-muted-foreground">{t('configOverridesDescription')}</p>
              {configSchema?.properties ? (
                <SchemaForm
                  schema={configSchema}
                  value={configOverrides}
                  onChange={setConfigOverrides}
                  disabled={loading}
                />
              ) : (
                <JsonEditor value={configOverrides} onChange={setConfigOverrides} disabled={loading} />
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)} disabled={loading}>
              {t('cancel')}
            </Button>
            <Button onClick={handleCreate} disabled={loading}>
              {t('create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('editDialogTitle')}</DialogTitle>
            <DialogDescription>
              {t('editDialogDescription', { name: selectedInstance?.instance_name })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('envOverrides')}</Label>
              <p className="text-xs text-muted-foreground">{t('envOverridesDescription')}</p>
              <KeyValueEditor
                value={envOverrides}
                onChange={setEnvOverrides}
                keyPlaceholder="ENV_VAR_NAME"
                valuePlaceholder="value"
                valueType="password"
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('configOverrides')}</Label>
              <p className="text-xs text-muted-foreground">{t('configOverridesDescription')}</p>
              {configSchema?.properties ? (
                <SchemaForm
                  schema={configSchema}
                  value={configOverrides}
                  onChange={setConfigOverrides}
                  disabled={loading}
                />
              ) : (
                <JsonEditor value={configOverrides} onChange={setConfigOverrides} disabled={loading} />
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)} disabled={loading}>
              {t('cancel')}
            </Button>
            <Button onClick={handleUpdate} disabled={loading}>
              {t('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteDialogTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteDialogDescription', { name: selectedInstance?.instance_name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={loading}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={loading}>
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
});

SkillInstanceManager.displayName = 'SkillInstanceManager';
