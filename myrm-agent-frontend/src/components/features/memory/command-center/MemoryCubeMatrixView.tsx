/**
 * [INPUT]
 * @/services/memory::MemoryCubeDTO, CubeRecordDTO, CreateCubeRequestDTO, CubeScopeType
 * onSelectCube: (cubeId: string) => void, selectedCubeId?: string
 * onCreateCube: (payload: CreateCubeRequestDTO) => Promise<void>
 * records: CubeRecordDTO[], isLoadingRecords: boolean
 *
 * [OUTPUT]
 * Component: MemoryCubeMatrixView
 *
 * [POS]
 * Matrix workspace presenting isolated memory cubes and partitioned records.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">`, visible focus rings,
 * proper htmlFor connections, and zero raw `>` or `->` characters.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Box, Lock, Globe, FolderGit2, User, Clock, Plus, FileText, ChevronRight } from 'lucide-react';
import type {
  CreateCubeRequestDTO,
  CubeRecordDTO,
  CubeScopeType,
  MemoryCubeDTO,
} from '@/services/memory';

interface MemoryCubeMatrixViewProps {
  cubes: MemoryCubeDTO[];
  selectedCubeId: string | null;
  onSelectCube: (cubeId: string) => void;
  records: CubeRecordDTO[];
  isLoadingRecords: boolean;
  onCreateCube: (payload: CreateCubeRequestDTO) => Promise<void>;
}

export const MemoryCubeMatrixView: React.FC<MemoryCubeMatrixViewProps> = ({
  cubes,
  selectedCubeId,
  onSelectCube,
  records,
  isLoadingRecords,
  onCreateCube,
}) => {
  const [filterScope, setFilterScope] = useState<CubeScopeType | 'all'>('all');
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newScope, setNewScope] = useState<CubeScopeType>('project_workspace');
  const [newDesc, setNewDesc] = useState('');
  const [newReadOnly, setNewReadOnly] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const filteredCubes = cubes.filter((c) =>
    filterScope === 'all' ? true : c.scope_type === filterScope
  );

  const activeCube = cubes.find((c) => c.cube_id === selectedCubeId) || null;

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      setIsSubmitting(true);
      await onCreateCube({
        name: newName.trim(),
        scope_type: newScope,
        description: newDesc.trim(),
        is_read_only: newReadOnly,
      });
      setNewName('');
      setNewDesc('');
      setIsCreating(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getScopeBadge = (scope: CubeScopeType) => {
    switch (scope) {
      case 'global_shared':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            <Globe className="w-3 h-3" aria-hidden="true" />
            Global Shared
          </span>
        );
      case 'project_workspace':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
            <FolderGit2 className="w-3 h-3" aria-hidden="true" />
            Workspace
          </span>
        );
      case 'agent_private':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
            <User className="w-3 h-3" aria-hidden="true" />
            Agent Private
          </span>
        );
      case 'ephemeral_task':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 border border-zinc-500/20">
            <Clock className="w-3 h-3" aria-hidden="true" />
            Ephemeral Task
          </span>
        );
    }
  };

  return (
    <section
      aria-label="Memory Cube Spatial Matrix"
      className="p-5 rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm space-y-4"
    >
      {/* Header & Filter Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Box className="w-4 h-4 text-primary" aria-hidden="true" />
            Memory Cube Spatial Matrix
          </h3>
          <p className="text-xs text-muted-foreground">
            Isolated compartment vaults preventing multi-agent cognitive cross-talk.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Scope Filter Tabs */}
          <div className="flex items-center p-0.5 rounded-lg border border-border/60 bg-muted/30 text-xs">
            {(['all', 'global_shared', 'project_workspace', 'agent_private', 'ephemeral_task'] as const).map(
              (tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setFilterScope(tab)}
                  className={`px-2.5 py-1 rounded-md font-medium transition-all focus:ring-2 focus:ring-primary focus:outline-none ${
                    filterScope === tab
                      ? 'bg-background text-foreground shadow-xs font-semibold'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tab === 'all'
                    ? 'All'
                    : tab === 'global_shared'
                    ? 'Global'
                    : tab === 'project_workspace'
                    ? 'Workspace'
                    : tab === 'agent_private'
                    ? 'Private'
                    : 'Ephemeral'}
                </button>
              )
            )}
          </div>

          <button
            type="button"
            onClick={() => setIsCreating(!isCreating)}
            aria-label="Provision new memory cube compartment"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:ring-2 focus:ring-primary focus:outline-none"
          >
            <Plus className="w-3.5 h-3.5" aria-hidden="true" />
            <span>New Cube</span>
          </button>
        </div>
      </div>

      {/* Inline Create Form */}
      {isCreating && (
        <form
          aria-label="Create new memory cube form"
          onSubmit={handleCreateSubmit}
          className="p-4 rounded-lg border border-primary/30 bg-primary/5 space-y-3"
        >
          <div className="text-xs font-semibold text-foreground">Provision Memory Cube</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="cube-name-input" className="block text-xs font-medium text-foreground mb-1">
                Cube Name
              </label>
              <input
                id="cube-name-input"
                type="text"
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Design Principles"
                className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground"
              />
            </div>
            <div>
              <label htmlFor="cube-scope-select" className="block text-xs font-medium text-foreground mb-1">
                Scope Boundary
              </label>
              <select
                id="cube-scope-select"
                value={newScope}
                onChange={(e) => setNewScope(e.target.value as CubeScopeType)}
                className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground"
              >
                <option value="project_workspace">project_workspace</option>
                <option value="agent_private">agent_private</option>
                <option value="global_shared">global_shared</option>
                <option value="ephemeral_task">ephemeral_task</option>
              </select>
            </div>
          </div>
          <div>
            <label htmlFor="cube-desc-input" className="block text-xs font-medium text-foreground mb-1">
              Purpose & Description
            </label>
            <input
              id="cube-desc-input"
              type="text"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Operational instructions and domain scope"
              className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground"
            />
          </div>
          <div className="flex items-center justify-between pt-1">
            <label htmlFor="cube-readonly-check" className="inline-flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input
                id="cube-readonly-check"
                type="checkbox"
                checked={newReadOnly}
                onChange={(e) => setNewReadOnly(e.target.checked)}
                className="rounded border-border text-primary focus:ring-2 focus:ring-primary focus:outline-none"
              />
              Enforce Read-Only (Forbidden to mutate without admin elevation)
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="px-2.5 py-1 text-xs rounded-md border border-border hover:bg-muted text-foreground focus:ring-2 focus:ring-primary focus:outline-none"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !newName.trim()}
                className="px-3 py-1 text-xs rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 focus:ring-2 focus:ring-primary focus:outline-none disabled:opacity-50"
              >
                {isSubmitting ? 'Creating...' : 'Create Cube'}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Main Grid: Cubes on the left, Records on the right */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
        {/* Cube Cards list */}
        <div className="md:col-span-5 space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
          {filteredCubes.map((cube) => {
            const isSelected = cube.cube_id === selectedCubeId;
            return (
              <button
                key={cube.cube_id}
                type="button"
                onClick={() => onSelectCube(cube.cube_id)}
                className={`w-full p-3 rounded-lg border text-left transition-all cursor-pointer focus:ring-2 focus:ring-primary focus:outline-none ${
                  isSelected
                    ? 'border-primary bg-primary/5 shadow-xs'
                    : 'border-border/60 bg-card hover:border-border hover:bg-muted/30'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="text-xs font-bold text-foreground truncate">{cube.name}</div>
                  {getScopeBadge(cube.scope_type)}
                </div>
                <p className="text-[11px] text-muted-foreground line-clamp-2 mb-2">
                  {cube.description || 'No description specified.'}
                </p>
                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1 font-mono">
                    <FileText className="w-3 h-3" aria-hidden="true" />
                    {cube.item_count} items
                  </span>
                  <div className="flex items-center gap-1.5">
                    {cube.is_read_only && (
                      <span className="inline-flex items-center gap-0.5 text-amber-500 font-medium">
                        <Lock className="w-3 h-3" aria-hidden="true" /> Read-Only
                      </span>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
                  </div>
                </div>
              </button>
            );
          })}
          {filteredCubes.length === 0 && (
            <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
              No memory cubes found matching the selected scope filter.
            </div>
          )}
        </div>

        {/* Selected Cube Records Detail View */}
        <div className="md:col-span-7 p-3.5 rounded-lg border border-border/60 bg-muted/10 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <div>
              <div className="text-xs font-semibold text-foreground">
                {activeCube ? activeCube.name : 'Select a Cube'}
              </div>
              <div className="text-[11px] text-muted-foreground font-mono">
                {activeCube ? activeCube.cube_id : 'Select a cube to inspect contained records'}
              </div>
            </div>
            {activeCube && getScopeBadge(activeCube.scope_type)}
          </div>

          {/* Records List */}
          <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
            {isLoadingRecords ? (
              <div className="p-6 text-center text-xs text-muted-foreground">
                Loading records from memory cube...
              </div>
            ) : records.length > 0 ? (
              records.map((rec) => (
                <div
                  key={rec.record_id}
                  className="p-2.5 rounded-md border border-border/40 bg-card text-xs space-y-1"
                >
                  <div className="text-[11px] font-mono text-muted-foreground flex items-center justify-between">
                    <span>{rec.record_id}</span>
                    <span>{new Date(rec.created_at * 1000).toLocaleTimeString()}</span>
                  </div>
                  <div className="text-foreground leading-relaxed font-sans">{rec.content}</div>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-md">
                No memory records found in this cube.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
