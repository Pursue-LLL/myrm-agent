'use client';

/**
 * [INPUT]
 * @/services/memory/domainMesh::getDomainMeshOverview, DomainMeshOverviewResponse, ProgressiveHighlight
 * ./DomainMeshCard::DomainMeshCard
 * ./MemoryDrillDownDialog::MemoryDrillDownDialog
 * ./HermesMigrationModal::HermesMigrationModal
 * lucide-react::RefreshCw, UploadCloud, Layers, Sparkles, AlertCircle
 *
 * [OUTPUT]
 * MemoryDomainMeshPanel: Dashboard panel rendering the Three-Domain Progressive Retrieval
 * and Hot-Cold Mirror Memory Mesh with lossless Hermes migration integration.
 *
 * [POS]
 * Primary UI component for Item 14 OpenViking-style three-domain progressive retrieval.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, UploadCloud, Layers, Sparkles, AlertCircle } from 'lucide-react';
import {
  getDomainMeshOverview,
  type DomainMeshOverviewResponse,
  type ProgressiveHighlight,
} from '@/services/memory/domainMesh';
import { DomainMeshCard } from './DomainMeshCard';
import { MemoryDrillDownDialog } from './MemoryDrillDownDialog';
import { HermesMigrationModal } from './HermesMigrationModal';
import { cn } from '@/lib/utils/classnameUtils';

interface MemoryDomainMeshPanelProps {
  className?: string;
}

export const MemoryDomainMeshPanel: React.FC<MemoryDomainMeshPanelProps> = ({ className }) => {
  const [data, setData] = useState<DomainMeshOverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedHighlight, setSelectedHighlight] = useState<ProgressiveHighlight | null>(null);
  const [drillDownOpen, setDrillDownOpen] = useState(false);
  const [migrationOpen, setMigrationOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getDomainMeshOverview();
      setData(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load domain mesh overview');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSelectHighlight = (highlight: ProgressiveHighlight) => {
    setSelectedHighlight(highlight);
    setDrillDownOpen(true);
  };

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {/* Top Header & Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-border/60 bg-card/40 p-4 backdrop-blur-sm shadow-xs">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 border border-primary/20 text-primary">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight text-foreground">
                Three-Domain Memory Mesh
              </h2>
              <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                Multi-Domain Sync
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Intelligently organizes preferences, persona, and task experiences for instant recall.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMigrationOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors shadow-xs"
          >
            <UploadCloud className="h-3.5 w-3.5" />
            <span>Migrate from Hermes</span>
          </button>
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            <span className="sr-only">Refresh</span>
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <button
            type="button"
            onClick={loadData}
            className="ml-auto underline font-medium hover:text-destructive/80"
          >
            Retry
          </button>
        </div>
      )}

      {/* Domain Cards Grid */}
      <div className="grid gap-4 md:grid-cols-3">
        <DomainMeshCard
          domain="user"
          title="User Domain"
          subtitle="Profile, Preferences & Events"
          data={data?.user}
          onSelectHighlight={handleSelectHighlight}
        />
        <DomainMeshCard
          domain="assistant"
          title="Assistant Domain"
          subtitle="Identity, Persona & Soul"
          data={data?.assistant}
          onSelectHighlight={handleSelectHighlight}
        />
        <DomainMeshCard
          domain="task"
          title="Task Domain"
          subtitle="Experiences, SOPs & Traps"
          data={data?.task}
          onSelectHighlight={handleSelectHighlight}
        />
      </div>

      {/* Drill-down Modal */}
      <MemoryDrillDownDialog
        memoryId={selectedHighlight?.id ?? null}
        open={drillDownOpen}
        onOpenChange={setDrillDownOpen}
      />

      {/* Hermes Migration Modal */}
      <HermesMigrationModal
        open={migrationOpen}
        onOpenChange={setMigrationOpen}
        onSuccess={loadData}
      />
    </div>
  );
};
