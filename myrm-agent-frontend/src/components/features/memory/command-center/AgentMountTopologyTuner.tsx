/**
 * [INPUT]
 * @/services/memory::MemoryCubeDTO, MountPolicyDTO, SetMountPolicyRequestDTO,
 *                    CubeQueryRequestDTO, CubeQueryResultDTO, CubeWriteRequestDTO, CubeWriteResultDTO
 * onUpdatePolicy: (agentId: string, payload: SetMountPolicyRequestDTO) => Promise<void>
 * onTestQuery: (payload: CubeQueryRequestDTO) => Promise<CubeQueryResultDTO>
 * onTestWrite: (payload: CubeWriteRequestDTO) => Promise<CubeWriteResultDTO>
 *
 * [OUTPUT]
 * Component: AgentMountTopologyTuner
 *
 * [POS]
 * Dynamic mount policy configurator and cross-talk barrier probe tester.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">`, visible focus rings,
 * proper htmlFor connections, and zero raw `>` or `->` characters.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Sliders, Shield, Search, Send, CheckCircle2, AlertTriangle } from 'lucide-react';
import type {
  CubeQueryRequestDTO,
  CubeQueryResultDTO,
  CubeWriteRequestDTO,
  CubeWriteResultDTO,
  MemoryCubeDTO,
  MountPolicyDTO,
  SetMountPolicyRequestDTO,
} from '@/services/memory';

interface AgentMountTopologyTunerProps {
  cubes: MemoryCubeDTO[];
  policies: MountPolicyDTO[];
  onUpdatePolicy: (agentId: string, payload: SetMountPolicyRequestDTO) => Promise<void>;
  onTestQuery: (payload: CubeQueryRequestDTO) => Promise<CubeQueryResultDTO>;
  onTestWrite: (payload: CubeWriteRequestDTO) => Promise<CubeWriteResultDTO>;
}

export const AgentMountTopologyTuner: React.FC<AgentMountTopologyTunerProps> = ({
  cubes,
  policies,
  onUpdatePolicy,
  onTestQuery,
  onTestWrite,
}) => {
  const [selectedAgentId, setSelectedAgentId] = useState<string>(
    policies[0]?.agent_id || 'agent-architect'
  );

  const currentPolicy =
    policies.find((p) => p.agent_id === selectedAgentId) || {
      agent_id: selectedAgentId,
      readable_cube_ids: cubes.map((c) => c.cube_id),
      writable_cube_ids: cubes.filter((c) => !c.is_read_only).map((c) => c.cube_id),
      default_write_cube_id: cubes.find((c) => !c.is_read_only)?.cube_id || null,
      strict_isolation: true,
    };

  // State for probe write test
  const [writeTargetCube, setWriteTargetCube] = useState<string>(
    currentPolicy.default_write_cube_id || cubes[0]?.cube_id || ''
  );
  const [writePayloadText, setWritePayloadText] = useState(
    'Probe write verification for memory cube barrier.'
  );
  const [writeResult, setWriteResult] = useState<CubeWriteResultDTO | null>(null);
  const [isWriting, setIsWriting] = useState(false);

  // State for federated query test
  const [queryKeyword, setQueryKeyword] = useState('Clean Architecture');
  const [queryResult, setQueryResult] = useState<CubeQueryResultDTO | null>(null);
  const [isQuerying, setIsQuerying] = useState(false);

  const toggleReadableCube = async (cubeId: string) => {
    const nextReadable = currentPolicy.readable_cube_ids.includes(cubeId)
      ? currentPolicy.readable_cube_ids.filter((id) => id !== cubeId)
      : [...currentPolicy.readable_cube_ids, cubeId];

    await onUpdatePolicy(selectedAgentId, {
      readable_cube_ids: nextReadable,
      writable_cube_ids: currentPolicy.writable_cube_ids,
      default_write_cube_id: currentPolicy.default_write_cube_id,
      strict_isolation: currentPolicy.strict_isolation,
    });
  };

  const toggleWritableCube = async (cubeId: string) => {
    const nextWritable = currentPolicy.writable_cube_ids.includes(cubeId)
      ? currentPolicy.writable_cube_ids.filter((id) => id !== cubeId)
      : [...currentPolicy.writable_cube_ids, cubeId];

    await onUpdatePolicy(selectedAgentId, {
      readable_cube_ids: currentPolicy.readable_cube_ids,
      writable_cube_ids: nextWritable,
      default_write_cube_id:
        currentPolicy.default_write_cube_id && nextWritable.includes(currentPolicy.default_write_cube_id)
          ? currentPolicy.default_write_cube_id
          : nextWritable[0] || null,
      strict_isolation: currentPolicy.strict_isolation,
    });
  };

  const handleStrictIsolationToggle = async () => {
    await onUpdatePolicy(selectedAgentId, {
      readable_cube_ids: currentPolicy.readable_cube_ids,
      writable_cube_ids: currentPolicy.writable_cube_ids,
      default_write_cube_id: currentPolicy.default_write_cube_id,
      strict_isolation: !currentPolicy.strict_isolation,
    });
  };

  const handleRunWriteProbe = async () => {
    if (!writePayloadText.trim()) return;
    try {
      setIsWriting(true);
      const res = await onTestWrite({
        agent_id: selectedAgentId,
        content: writePayloadText.trim(),
        target_cube_id: writeTargetCube || undefined,
      });
      setWriteResult(res);
    } finally {
      setIsWriting(false);
    }
  };

  const handleRunFederatedQuery = async () => {
    if (!queryKeyword.trim()) return;
    try {
      setIsQuerying(true);
      const res = await onTestQuery({
        agent_id: selectedAgentId,
        query: queryKeyword.trim(),
        limit: 5,
      });
      setQueryResult(res);
    } finally {
      setIsQuerying(false);
    }
  };

  return (
    <section
      aria-label="Agent Dynamic Mount Topology Tuner"
      className="p-5 rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm space-y-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Sliders className="w-4 h-4 text-primary" aria-hidden="true" />
            Dynamic Mount Topology &amp; Read/Write Decoupling
          </h3>
          <p className="text-xs text-muted-foreground">
            Configure read-federated and write-isolated compartments per sub-agent.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="agent-picker-select" className="text-xs font-medium text-foreground">
            Target Agent:
          </label>
          <select
            id="agent-picker-select"
            value={selectedAgentId}
            onChange={(e) => {
              setSelectedAgentId(e.target.value);
              setWriteResult(null);
              setQueryResult(null);
            }}
            className="px-2.5 py-1 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground font-mono"
          >
            {policies.map((p) => (
              <option key={p.agent_id} value={p.agent_id}>
                {p.agent_id}
              </option>
            ))}
            {!policies.some((p) => p.agent_id === 'agent-custom') && (
              <option value="agent-custom">agent-custom</option>
            )}
          </select>
        </div>
      </div>

      {/* Mounting Matrix Configuration */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Readable Cubes list */}
        <div className="p-3.5 rounded-lg border border-border/40 bg-muted/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Search className="w-3.5 h-3.5 text-blue-500" aria-hidden="true" />
              Readable Cubes (Federated Scope)
            </span>
            <span className="text-[11px] text-muted-foreground">
              {currentPolicy.readable_cube_ids.length} selected
            </span>
          </div>
          <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
            {cubes.map((cube) => {
              const isChecked = currentPolicy.readable_cube_ids.includes(cube.cube_id);
              return (
                <label
                  key={cube.cube_id}
                  htmlFor={`readable-${cube.cube_id}`}
                  className="flex items-center justify-between p-2 rounded-md border border-border/40 bg-card hover:bg-muted/40 cursor-pointer text-xs"
                >
                  <div className="flex items-center gap-2">
                    <input
                      id={`readable-${cube.cube_id}`}
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleReadableCube(cube.cube_id)}
                      className="rounded border-border text-primary focus:ring-2 focus:ring-primary focus:outline-none"
                    />
                    <span className="font-medium text-foreground">{cube.name}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground font-mono">{cube.scope_type}</span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Writable Cubes list & Strict Isolation */}
        <div className="p-3.5 rounded-lg border border-border/40 bg-muted/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-purple-500" aria-hidden="true" />
              Writable Cubes (Mutation Isolation)
            </span>
            <span className="text-[11px] text-muted-foreground">
              {currentPolicy.writable_cube_ids.length} authorized
            </span>
          </div>
          <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
            {cubes.map((cube) => {
              const isChecked = currentPolicy.writable_cube_ids.includes(cube.cube_id);
              return (
                <label
                  key={cube.cube_id}
                  htmlFor={`writable-${cube.cube_id}`}
                  className="flex items-center justify-between p-2 rounded-md border border-border/40 bg-card hover:bg-muted/40 cursor-pointer text-xs"
                >
                  <div className="flex items-center gap-2">
                    <input
                      id={`writable-${cube.cube_id}`}
                      type="checkbox"
                      checked={isChecked}
                      disabled={cube.is_read_only}
                      onChange={() => toggleWritableCube(cube.cube_id)}
                      className="rounded border-border text-primary focus:ring-2 focus:ring-primary focus:outline-none disabled:opacity-40"
                    />
                    <span className={`font-medium ${cube.is_read_only ? 'text-muted-foreground line-through' : 'text-foreground'}`}>
                      {cube.name}
                    </span>
                  </div>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {cube.is_read_only ? 'Immutable' : cube.scope_type}
                  </span>
                </label>
              );
            })}
          </div>
          <div className="pt-2 border-t border-border/30 flex items-center justify-between">
            <label htmlFor="strict-iso-toggle" className="inline-flex items-center gap-2 text-xs text-foreground cursor-pointer">
              <input
                id="strict-iso-toggle"
                type="checkbox"
                checked={currentPolicy.strict_isolation}
                onChange={handleStrictIsolationToggle}
                className="rounded border-border text-primary focus:ring-2 focus:ring-primary focus:outline-none"
              />
              Enforce Strict Cross-Talk Blocking
            </label>
          </div>
        </div>
      </div>

      {/* Live Probe Verification Tabs: Write Barrier Test & Federated Query Test */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
        {/* Write Barrier Probe */}
        <div className="p-3.5 rounded-lg border border-border/60 bg-card space-y-3">
          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Send className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
            Write Barrier Probe
          </div>
          <div className="space-y-2">
            <div>
              <label htmlFor="probe-target-select" className="block text-[11px] font-medium text-muted-foreground mb-1">
                Target Memory Cube:
              </label>
              <select
                id="probe-target-select"
                value={writeTargetCube}
                onChange={(e) => setWriteTargetCube(e.target.value)}
                className="w-full px-2 py-1 text-xs rounded border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground font-mono"
              >
                {cubes.map((c) => (
                  <option key={c.cube_id} value={c.cube_id}>
                    {c.name} ({c.cube_id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="probe-content-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
                Probe Memory Content:
              </label>
              <input
                id="probe-content-input"
                type="text"
                value={writePayloadText}
                onChange={(e) => setWritePayloadText(e.target.value)}
                className="w-full px-2 py-1 text-xs rounded border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground"
              />
            </div>
            <button
              type="button"
              onClick={handleRunWriteProbe}
              disabled={isWriting}
              className="w-full py-1.5 px-3 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:ring-2 focus:ring-primary focus:outline-none disabled:opacity-50"
            >
              {isWriting ? 'Probing...' : 'Dispatch Write Probe'}
            </button>
            {writeResult && (
              <div
                className={`p-2 rounded text-xs border ${
                  writeResult.success
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                    : 'bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  {writeResult.success ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                      Write Authorized &amp; Committed
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
                      Write Blocked by Isolation Firewall
                    </>
                  )}
                </div>
                <div className="text-[11px] mt-0.5 opacity-90">
                  {writeResult.success
                    ? `Destination: ${writeResult.destination_cube_id}`
                    : writeResult.rejection_reason}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Federated Query Probe */}
        <div className="p-3.5 rounded-lg border border-border/60 bg-card space-y-3">
          <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5 text-blue-500" aria-hidden="true" />
            Federated Query Verification
          </div>
          <div className="space-y-2">
            <div>
              <label htmlFor="federated-query-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
                Query String across Mounted Readable Cubes:
              </label>
              <input
                id="federated-query-input"
                type="text"
                value={queryKeyword}
                onChange={(e) => setQueryKeyword(e.target.value)}
                placeholder="Search across readable cubes"
                className="w-full px-2 py-1 text-xs rounded border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground"
              />
            </div>
            <button
              type="button"
              onClick={handleRunFederatedQuery}
              disabled={isQuerying}
              className="w-full py-1.5 px-3 text-xs font-medium rounded-md border border-border bg-secondary hover:bg-secondary/80 text-secondary-foreground transition-colors focus:ring-2 focus:ring-primary focus:outline-none disabled:opacity-50"
            >
              {isQuerying ? 'Searching...' : 'Execute Federated Query'}
            </button>
            {queryResult && (
              <div className="p-2 rounded text-xs border border-border/60 bg-muted/20 space-y-1">
                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Found {queryResult.total_found} hits</span>
                  <span>{queryResult.query_duration_ms} ms</span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Queried Cubes: {queryResult.queried_cube_ids.join(', ') || 'none'}
                </div>
                <div className="max-h-[80px] overflow-y-auto space-y-1 pt-1">
                  {queryResult.items.map((it) => (
                    <div key={it.record_id} className="text-[11px] p-1 rounded bg-card border border-border/30">
                      <span className="font-mono text-muted-foreground mr-1">[{it.cube_id}]:</span>
                      <span>{it.content}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
