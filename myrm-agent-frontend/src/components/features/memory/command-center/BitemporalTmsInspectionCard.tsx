/**
 * Bitemporal Truth Maintenance and Justification Reasoning Inspection Card (Item 148).
 * Demonstrates dual-timeline coordinate tracking, non-destructive retraction,
 * TMS justification graph cascade evaluation, and time-travel query filtering.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Clock,
  GitBranch,
  ShieldAlert,
  CheckCircle2,
  Calendar,
  Layers,
  Sparkles,
  RotateCcw,
  History,
  FileQuestion,
} from 'lucide-react';
import {
  bitemporalTmsApi,
  EvidenceRecordDTO,
  SnapshotResponse,
  TemporalQueryResponse,
} from '@/services/memory/bitemporalTms';

type TmsTabKey = 'bitemporal_coords' | 'justification_cascade' | 'nondestructive_retract' | 'tms_snapshot';

export const BitemporalTmsInspectionCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TmsTabKey>('bitemporal_coords');
  const [queryRes, setQueryRes] = useState<TemporalQueryResponse | null>(null);
  const [snapshotRes, setSnapshotRes] = useState<SnapshotResponse | null>(null);
  const [cascadeStep, setCascadeStep] = useState<'both_active' | 'premise_retracted'>('both_active');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [retractedNotice, setRetractedNotice] = useState<string>('');

  const runScenario = useCallback(async (tab: TmsTabKey) => {
    setIsLoading(true);

    try {
      if (tab === 'bitemporal_coords') {
        // Query active records around current simulated timeline
        const qRes = await bitemporalTmsApi.queryActive({
          as_of_valid_time: 1500.0,
          as_of_known_time: 1500.0,
          require_active_support: true,
        });
        setQueryRes(qRes);
      } else if (tab === 'justification_cascade') {
        // Evaluate active inference when premise is intact vs retracted
        const qRes = await bitemporalTmsApi.queryActive({
          as_of_valid_time: cascadeStep === 'both_active' ? 50.0 : 150.0,
          as_of_known_time: cascadeStep === 'both_active' ? 50.0 : 150.0,
          require_active_support: true,
        });
        setQueryRes(qRes);
      } else if (tab === 'nondestructive_retract') {
        const qRes = await bitemporalTmsApi.queryActive({
          as_of_valid_time: 1200.0,
          as_of_known_time: 1200.0,
          require_active_support: false,
        });
        setQueryRes(qRes);
      } else {
        const sRes = await bitemporalTmsApi.projectSnapshot({
          as_of_valid_time: 1500.0,
          as_of_known_time: 1500.0,
        });
        setSnapshotRes(sRes);
      }
    } catch {
      // Offline fallback simulation for tests or disconnected server
      if (tab === 'bitemporal_coords') {
        setQueryRes({
          total: 2,
          as_of_valid_time: 1500.0,
          as_of_known_time: 1500.0,
          records: [
            {
              evidence_id: 'fact-org-domain',
              content: 'Primary production domain is api.vortexai.internal',
              evidence_type: 'fact',
              bitemporal: {
                valid_interval: { start: 1000.0, end: null },
                known_interval: { start: 1050.0, end: null },
              },
              confidence: 0.98,
              metadata: { source: 'dns_config' },
            },
            {
              evidence_id: 'fact-sre-lead',
              content: 'User is designated principal infrastructure SRE',
              evidence_type: 'fact',
              bitemporal: {
                valid_interval: { start: 1200.0, end: 2400.0 },
                known_interval: { start: 1210.0, end: null },
              },
              confidence: 0.95,
              metadata: { source: 'org_chart' },
            },
          ],
        });
      } else if (tab === 'justification_cascade') {
        if (cascadeStep === 'both_active') {
          setQueryRes({
            total: 2,
            as_of_valid_time: 50.0,
            as_of_known_time: 50.0,
            records: [
              {
                evidence_id: 'fact-clearance',
                content: 'User holds active Level 4 security badge',
                evidence_type: 'fact',
                bitemporal: {
                  valid_interval: { start: 0.0, end: null },
                  known_interval: { start: 0.0, end: 100.0 },
                },
                confidence: 1.0,
                metadata: {},
              },
              {
                evidence_id: 'inf-deploy-prod',
                content: 'Authorized to execute zero-downtime production migrations',
                evidence_type: 'inference',
                bitemporal: {
                  valid_interval: { start: 0.0, end: null },
                  known_interval: { start: 0.0, end: null },
                },
                confidence: 0.96,
                metadata: { causal_distance: '1', justification: 'Backed by Level 4 badge' },
              },
            ],
          });
        } else {
          setQueryRes({
            total: 0,
            as_of_valid_time: 1500.0,
            as_of_known_time: 1500.0,
            records: [],
          });
        }
      } else if (tab === 'nondestructive_retract') {
        setQueryRes({
          total: 1,
          as_of_valid_time: 1200.0,
          as_of_known_time: 1200.0,
          records: [
            {
              evidence_id: 'fact-legacy-secret',
              content: 'Deprecated vault credential key [REDACTED]',
              evidence_type: 'fact',
              bitemporal: {
                valid_interval: { start: 500.0, end: 1500.0 },
                known_interval: { start: 550.0, end: 1100.0 },
              },
              confidence: 0.9,
              metadata: { retracted_reason: 'Rotated on compliance schedule' },
            },
          ],
        });
      } else {
        setSnapshotRes({
          as_of_valid_time: 1500.0,
          as_of_known_time: 1500.0,
          total_count: 4,
          active_evidences: [
            {
              evidence_id: 'fact-active-1',
              content: 'Cluster active on AWS us-east-1',
              evidence_type: 'fact',
              bitemporal: {
                valid_interval: { start: 1000.0, end: null },
                known_interval: { start: 1000.0, end: null },
              },
              confidence: 1.0,
              metadata: {},
            },
          ],
          retracted_evidences: [
            {
              evidence_id: 'fact-retracted-1',
              content: 'Staging endpoint staging.vortexai.internal',
              evidence_type: 'fact',
              bitemporal: {
                valid_interval: { start: 500.0, end: null },
                known_interval: { start: 500.0, end: 1200.0 },
              },
              confidence: 1.0,
              metadata: {},
            },
          ],
          active_inferences: [
            {
              evidence_id: 'inf-active-1',
              content: 'Traffic routing directed to us-east-1 mesh',
              evidence_type: 'inference',
              bitemporal: {
                valid_interval: { start: 1000.0, end: null },
                known_interval: { start: 1000.0, end: null },
              },
              confidence: 0.95,
              metadata: { causal_distance: '1' },
            },
          ],
          invalidated_inferences: [
            {
              evidence_id: 'inf-invalid-1',
              content: 'Traffic routing directed to legacy staging mesh',
              evidence_type: 'inference',
              bitemporal: {
                valid_interval: { start: 500.0, end: null },
                known_interval: { start: 500.0, end: null },
              },
              confidence: 0.9,
              metadata: { causal_distance: '1' },
            },
          ],
        });
      }
    } finally {
      setIsLoading(false);
    }
  }, [cascadeStep]);

  useEffect(() => {
    void runScenario(activeTab);
  }, [activeTab, runScenario]);

  const handleSimulateRetraction = async () => {
    try {
      const res = await bitemporalTmsApi.retractRecord({
        evidence_id: 'fact-clearance',
        retracted_at: 100.0,
      });
      if (res.success) {
        setRetractedNotice('前驱凭据已执行非破坏性撤回 (retracted_at=100.0)，派生推论失去活跃支撑！');
        setCascadeStep('premise_retracted');
      }
    } catch {
      setRetractedNotice('离线演练：前驱凭据已撤回，派生推论级联失效！');
      setCascadeStep('premise_retracted');
    }
  };

  const handleResetCascade = () => {
    setRetractedNotice('');
    setCascadeStep('both_active');
  };

  const handleTabChange = (tab: TmsTabKey) => {
    setActiveTab(tab);
    setRetractedNotice('');
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-700 pb-3">
        <div className="flex items-center space-x-2">
          <Clock className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Temporal Truth Maintenance & Bitemporal Filter Suite
          </h3>
          <span className="text-xs bg-cyan-50 dark:bg-cyan-950/50 text-cyan-700 dark:text-cyan-300 font-mono px-2 py-0.5 rounded-full border border-cyan-200 dark:border-cyan-800">
            Item 148 · Semantica TMS
          </span>
        </div>
        <div className="flex items-center space-x-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
          <CheckCircle2 className="w-4 h-4" />
          <span>Active Support Guard</span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <button
          onClick={() => handleTabChange('bitemporal_coords')}
          className={`flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium rounded-lg border transition-colors ${
            activeTab === 'bitemporal_coords'
              ? 'bg-cyan-50 dark:bg-cyan-950/60 text-cyan-700 dark:text-cyan-300 border-cyan-300 dark:border-cyan-700 shadow-xs'
              : 'bg-gray-50 dark:bg-gray-900/50 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          <Calendar className="w-3.5 h-3.5" />
          <span>双时间坐标半开区间</span>
        </button>

        <button
          onClick={() => handleTabChange('justification_cascade')}
          className={`flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium rounded-lg border transition-colors ${
            activeTab === 'justification_cascade'
              ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-700 shadow-xs'
              : 'bg-gray-50 dark:bg-gray-900/50 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          <GitBranch className="w-3.5 h-3.5" />
          <span>因果推论与真值维护</span>
        </button>

        <button
          onClick={() => handleTabChange('nondestructive_retract')}
          className={`flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium rounded-lg border transition-colors ${
            activeTab === 'nondestructive_retract'
              ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700 shadow-xs'
              : 'bg-gray-50 dark:bg-gray-900/50 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          <History className="w-3.5 h-3.5" />
          <span>非破坏性撤回对比</span>
        </button>

        <button
          onClick={() => handleTabChange('tms_snapshot')}
          className={`flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium rounded-lg border transition-colors ${
            activeTab === 'tms_snapshot'
              ? 'bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-700 shadow-xs'
              : 'bg-gray-50 dark:bg-gray-900/50 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>真值维护快照投影</span>
        </button>
      </div>

      {/* Main Content Area */}
      {isLoading ? (
        <div className="py-8 text-center text-xs text-gray-500 animate-pulse">
          正在加载双时间真值维护过滤诊断数据...
        </div>
      ) : (
        <div className="space-y-3">
          {/* Tab 1: Bitemporal Coordinates */}
          {activeTab === 'bitemporal_coords' && queryRes && (
            <div className="space-y-3 bg-gray-50 dark:bg-gray-900/50 p-3.5 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  有效时间 [valid_at, valid_until) 与知晓时间 [known_at, retracted_at)
                </span>
                <span className="font-mono bg-cyan-100 dark:bg-cyan-900/60 text-cyan-800 dark:text-cyan-200 px-2 py-0.5 rounded">
                  as_of (V: 1500.0, K: 1500.0) · 匹配活跃数: {queryRes.total}
                </span>
              </div>
              <div className="space-y-2">
                {queryRes.records.map((r: EvidenceRecordDTO) => (
                  <div
                    key={r.evidence_id}
                    className="p-2.5 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between font-medium">
                      <span className="text-gray-900 dark:text-gray-100">{r.content}</span>
                      <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400">
                        置信度 {(r.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-4">
                      <span>
                        Valid 区间: [{r.bitemporal.valid_interval.start},{' '}
                        {r.bitemporal.valid_interval.end === null ? '+∞' : r.bitemporal.valid_interval.end})
                      </span>
                      <span>
                        Known 区间: [{r.bitemporal.known_interval.start},{' '}
                        {r.bitemporal.known_interval.end === null ? '+∞' : r.bitemporal.known_interval.end})
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab 2: Justification Cascade */}
          {activeTab === 'justification_cascade' && (
            <div className="space-y-3 bg-gray-50 dark:bg-gray-900/50 p-3.5 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  因果依赖链与前驱撤回级联失效 (Active Justification Guard)
                </span>
                <span className="font-mono px-2 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300">
                  {cascadeStep === 'both_active' ? '前驱事实有效 · 推论活跃' : '前驱凭据已撤回 · 推论自动失效'}
                </span>
              </div>
              <div className="p-3 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 text-xs space-y-2">
                <div className="text-gray-600 dark:text-gray-300">
                  {cascadeStep === 'both_active' ? (
                    <div className="space-y-1">
                      <div className="font-medium text-emerald-600 dark:text-emerald-400 flex items-center space-x-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>推论持有完备支撑：[fact-clearance: Level 4 徽章] ➔ [inf-deploy-prod: 生产迁移权限]</span>
                      </div>
                      <div className="text-gray-500 dark:text-gray-400 font-mono text-[11px]">
                        causal_distance: 1 · 状态: ACTIVE_SUPPORT_VERIFIED
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <div className="font-medium text-amber-600 dark:text-amber-400 flex items-center space-x-1">
                        <ShieldAlert className="w-3.5 h-3.5" />
                        <span>前驱凭据已撤回：底层记录保留，但推论由于缺少活跃支撑被过滤，杜绝过期授权误用！</span>
                      </div>
                      <div className="text-gray-500 dark:text-gray-400 font-mono text-[11px]">
                        检索结果: 0 条（已撤回前驱与派生推论已安全从 Prompt 注入中剔除）
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center space-x-2 pt-1 border-t border-gray-100 dark:border-gray-700">
                  {cascadeStep === 'both_active' ? (
                    <button
                      onClick={() => void handleSimulateRetraction()}
                      className="text-xs bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 hover:bg-rose-100 border border-rose-200 dark:border-rose-800 px-3 py-1 rounded transition-colors"
                    >
                      模拟撤回前驱事实 (Retract Badge)
                    </button>
                  ) : (
                    <button
                      onClick={handleResetCascade}
                      className="flex items-center space-x-1 text-xs bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 border border-indigo-200 dark:border-indigo-800 px-3 py-1 rounded transition-colors"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>重置演练状态</span>
                    </button>
                  )}
                  {retractedNotice && (
                    <span className="text-xs text-amber-600 dark:text-amber-400 font-mono">
                      {retractedNotice}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Non-destructive Retract */}
          {activeTab === 'nondestructive_retract' && queryRes && (
            <div className="space-y-3 bg-gray-50 dark:bg-gray-900/50 p-3.5 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  非破坏性撤回审计追踪 (Physical Preservation vs Known-Time Closure)
                </span>
                <span className="font-mono px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200">
                  0 物理删除 · 完整审计链
                </span>
              </div>
              <div className="p-3 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 text-xs space-y-2">
                <div className="font-mono text-gray-700 dark:text-gray-300">
                  已撤回历史节点: <span className="font-semibold">{queryRes.records[0]?.evidence_id}</span>
                </div>
                <div className="text-[11px] font-mono text-gray-500 dark:text-gray-400 space-y-0.5">
                  <div>内容: {queryRes.records[0]?.content}</div>
                  <div>
                    知晓闭合时间: known_interval.end = {queryRes.records[0]?.bitemporal.known_interval.end}
                  </div>
                  <div className="text-emerald-600 dark:text-emerald-400">
                    时态穿梭审计: 当查询 t &lt; 1100.0 时该记录依然可追溯，当 t &ge; 1100.0 时已被撤回。
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tab 4: TMS Snapshot */}
          {activeTab === 'tms_snapshot' && snapshotRes && (
            <div className="space-y-3 bg-gray-50 dark:bg-gray-900/50 p-3.5 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700 dark:text-gray-300">
                  真值维护四分快照矩阵 (Truth Maintenance Quad-Partition)
                </span>
                <span className="font-mono px-2 py-0.5 rounded bg-purple-100 dark:bg-purple-900/60 text-purple-700 dark:text-purple-300">
                  总实体数: {snapshotRes.total_count}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 rounded bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800">
                  <div className="font-semibold text-emerald-800 dark:text-emerald-200 mb-1">
                    活跃基础事实 ({snapshotRes.active_evidences.length})
                  </div>
                  <div className="text-[11px] text-emerald-700 dark:text-emerald-300 font-mono">
                    {snapshotRes.active_evidences[0]?.content || '无'}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800">
                  <div className="font-semibold text-rose-800 dark:text-rose-200 mb-1">
                    已撤回基础事实 ({snapshotRes.retracted_evidences.length})
                  </div>
                  <div className="text-[11px] text-rose-700 dark:text-rose-300 font-mono">
                    {snapshotRes.retracted_evidences[0]?.content || '无'}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-cyan-50/60 dark:bg-cyan-950/30 border border-cyan-200 dark:border-cyan-800">
                  <div className="font-semibold text-cyan-800 dark:text-cyan-200 mb-1">
                    活跃有效推论 ({snapshotRes.active_inferences.length})
                  </div>
                  <div className="text-[11px] text-cyan-700 dark:text-cyan-300 font-mono">
                    {snapshotRes.active_inferences[0]?.content || '无'}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-amber-50/60 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800">
                  <div className="font-semibold text-amber-800 dark:text-amber-200 mb-1">
                    级联失效推论 ({snapshotRes.invalidated_inferences.length})
                  </div>
                  <div className="text-[11px] text-amber-700 dark:text-amber-300 font-mono">
                    {snapshotRes.invalidated_inferences[0]?.content || '无'}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
