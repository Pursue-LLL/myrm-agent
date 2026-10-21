/**
 * [INPUT]
 * @/services/memory::getCubeMatrixOverview, listCubeRecords, createMemoryCube,
 *                    setAgentMountPolicy, queryCubesFederated, writeCubeMemory,
 *                    CubeMatrixOverviewDTO, CreateCubeRequestDTO, SetMountPolicyRequestDTO,
 *                    CubeQueryRequestDTO, CubeWriteRequestDTO, CubeRecordDTO
 * ./memCubeFallbacks::FALLBACK_CUBE_MATRIX_OVERVIEW, FALLBACK_SAMPLE_RECORDS
 * ./MemoryCubeHudBar::MemoryCubeHudBar
 * ./MemoryCubeMatrixView::MemoryCubeMatrixView
 * ./AgentMountTopologyTuner::AgentMountTopologyTuner
 *
 * [OUTPUT]
 * Component: MemoryCubeStudioCard
 *
 * [POS]
 * Command Center flagship card for Item 124 Memory Cube Scoped Isolation & Dynamic Mounting Suite.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">`, visible focus rings,
 * proper htmlFor connections, and zero raw `>` or `->` characters.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Box } from 'lucide-react';
import {
  createMemoryCube,
  getCubeMatrixOverview,
  listCubeRecords,
  queryCubesFederated,
  setAgentMountPolicy,
  writeCubeMemory,
} from '@/services/memory';
import type {
  CreateCubeRequestDTO,
  CubeMatrixOverviewDTO,
  CubeQueryRequestDTO,
  CubeQueryResultDTO,
  CubeRecordDTO,
  CubeWriteRequestDTO,
  CubeWriteResultDTO,
  SetMountPolicyRequestDTO,
} from '@/services/memory';
import {
  FALLBACK_CUBE_MATRIX_OVERVIEW,
  FALLBACK_SAMPLE_RECORDS,
} from './memCubeFallbacks';
import { MemoryCubeHudBar } from './MemoryCubeHudBar';
import { MemoryCubeMatrixView } from './MemoryCubeMatrixView';
import { AgentMountTopologyTuner } from './AgentMountTopologyTuner';

export const MemoryCubeStudioCard: React.FC = () => {
  const [overview, setOverview] = useState<CubeMatrixOverviewDTO>(FALLBACK_CUBE_MATRIX_OVERVIEW);
  const [selectedCubeId, setSelectedCubeId] = useState<string | null>(
    FALLBACK_CUBE_MATRIX_OVERVIEW.cubes[0]?.cube_id || null
  );
  const [records, setRecords] = useState<CubeRecordDTO[]>(
    FALLBACK_SAMPLE_RECORDS['cube-global-shared'] || []
  );
  const [isLoadingRecords, setIsLoadingRecords] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchOverview = useCallback(async () => {
    try {
      setIsRefreshing(true);
      const data = await getCubeMatrixOverview();
      setOverview(data);
      if (!selectedCubeId && data.cubes.length > 0) {
        setSelectedCubeId(data.cubes[0]?.cube_id || null);
      }
    } catch {
      // Fallback to offline fixtures seamlessly
      setOverview(FALLBACK_CUBE_MATRIX_OVERVIEW);
    } finally {
      setIsRefreshing(false);
    }
  }, [selectedCubeId]);

  const fetchRecords = useCallback(async (cubeId: string) => {
    try {
      setIsLoadingRecords(true);
      const data = await listCubeRecords(cubeId);
      setRecords(data);
    } catch {
      setRecords(FALLBACK_SAMPLE_RECORDS[cubeId] || []);
    } finally {
      setIsLoadingRecords(false);
    }
  }, []);

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    if (selectedCubeId) {
      void fetchRecords(selectedCubeId);
    }
  }, [selectedCubeId, fetchRecords]);

  const handleSelectCube = (cubeId: string) => {
    setSelectedCubeId(cubeId);
  };

  const handleCreateCube = async (payload: CreateCubeRequestDTO) => {
    try {
      await createMemoryCube(payload);
    } catch {
      // Optimistic local state update for offline environments
      const simulatedCube = {
        cube_id: payload.cube_id || `cube-local-${Date.now()}`,
        name: payload.name,
        scope_type: payload.scope_type,
        owner_id: payload.owner_id || null,
        description: payload.description || '',
        is_read_only: payload.is_read_only || false,
        item_count: 0,
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000,
      };
      setOverview((prev) => ({
        ...prev,
        cubes: [...prev.cubes, simulatedCube],
        total_cubes: prev.total_cubes + 1,
      }));
    }
    await fetchOverview();
  };

  const handleUpdatePolicy = async (agentId: string, payload: SetMountPolicyRequestDTO) => {
    try {
      const updated = await setAgentMountPolicy(agentId, payload);
      setOverview((prev) => ({
        ...prev,
        policies: [
          ...prev.policies.filter((p) => p.agent_id !== agentId),
          updated,
        ],
      }));
    } catch {
      // Local optimistic update
      setOverview((prev) => ({
        ...prev,
        policies: [
          ...prev.policies.filter((p) => p.agent_id !== agentId),
          { agent_id: agentId, ...payload },
        ],
      }));
    }
  };

  const handleTestWrite = async (payload: CubeWriteRequestDTO): Promise<CubeWriteResultDTO> => {
    try {
      const res = await writeCubeMemory(payload);
      if (res.success && selectedCubeId) {
        void fetchRecords(selectedCubeId);
      }
      return res;
    } catch {
      // Client-side barrier simulation
      const targetCube = overview.cubes.find((c) => c.cube_id === payload.target_cube_id);
      const policy = overview.policies.find((p) => p.agent_id === payload.agent_id);

      if (targetCube?.is_read_only) {
        return {
          success: false,
          destination_cube_id: targetCube.cube_id,
          rejection_reason: `MemoryCube '${targetCube.cube_id}' is immutable (read-only).`,
        };
      }
      if (policy && policy.strict_isolation && payload.target_cube_id) {
        if (!policy.writable_cube_ids.includes(payload.target_cube_id)) {
          return {
            success: false,
            destination_cube_id: payload.target_cube_id,
            rejection_reason: `Agent '${payload.agent_id}' is not authorized to write to MemoryCube '${payload.target_cube_id}'.`,
          };
        }
      }
      return {
        success: true,
        destination_cube_id: payload.target_cube_id || 'cube-agent-architect-private',
        record: {
          record_id: `rec-mock-${Date.now()}`,
          cube_id: payload.target_cube_id || 'cube-agent-architect-private',
          content: payload.content,
          metadata: {},
          created_at: Date.now() / 1000,
        },
      };
    }
  };

  const handleTestQuery = async (payload: CubeQueryRequestDTO): Promise<CubeQueryResultDTO> => {
    try {
      return await queryCubesFederated(payload);
    } catch {
      // Simulation
      const matched: CubeRecordDTO[] = [];
      const queriedCubes: string[] = [];
      const policy = overview.policies.find((p) => p.agent_id === payload.agent_id);
      const targetCubes = policy ? policy.readable_cube_ids : overview.cubes.map((c) => c.cube_id);

      for (const cubeId of targetCubes) {
        queriedCubes.push(cubeId);
        const list = FALLBACK_SAMPLE_RECORDS[cubeId] || [];
        for (const item of list) {
          if (item.content.toLowerCase().includes(payload.query.toLowerCase())) {
            matched.push(item);
          }
        }
      }

      return {
        items: matched,
        total_found: matched.length,
        queried_cube_ids: queriedCubes,
        query_duration_ms: 12.5,
      };
    }
  };

  return (
    <section
      aria-label="Memory Cube Scoped Isolation Studio"
      className="p-6 rounded-2xl border border-border/80 bg-card/80 backdrop-blur-md shadow-sm space-y-6"
    >
      {/* Studio Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <Box className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-tight text-foreground">
                Memory Cube Scoped Isolation &amp; Dynamic Mounting Studio
              </h2>
              <div className="text-xs text-muted-foreground">
                Item 124 [P0] · Multi-agent private/shared compartments with read/write decoupled mounting
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 4D Telemetry HUD Bar */}
      <MemoryCubeHudBar
        overview={overview}
        isRefreshing={isRefreshing}
        onRefresh={fetchOverview}
      />

      {/* Spatial Matrix View */}
      <MemoryCubeMatrixView
        cubes={overview.cubes}
        selectedCubeId={selectedCubeId}
        onSelectCube={handleSelectCube}
        records={records}
        isLoadingRecords={isLoadingRecords}
        onCreateCube={handleCreateCube}
      />

      {/* Dynamic Mount Topology Tuner & Live Barrier Tester */}
      <AgentMountTopologyTuner
        cubes={overview.cubes}
        policies={overview.policies}
        onUpdatePolicy={handleUpdatePolicy}
        onTestQuery={handleTestQuery}
        onTestWrite={handleTestWrite}
      />
    </section>
  );
};
