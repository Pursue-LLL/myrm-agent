'use client';

/**
 * MyMachinesSection Component.
 * Self-hosted machine fleet dashboard displaying node cards, real-time telemetry,
 * and live screen takeover launcher. Adheres to Cursor "My Machines" paradigm with zero emojis.
 */

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  Cpu,
  HardDrive,
  Laptop,
  Plus,
  Radio,
  RefreshCw,
  Server,
  Tv,
} from 'lucide-react';
import { MachineNode, MachineStatus } from './machinesTypes';
import { MachinesService } from './machinesService';
import { ConnectMachineModal } from './ConnectMachineModal';
import { LiveTakeoverDrawer } from './LiveTakeoverDrawer';

export const MyMachinesSection: React.FC = () => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('machines');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [machines, setMachines] = useState<MachineNode[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState<boolean>(false);
  const [selectedMachineForTakeover, setSelectedMachineForTakeover] = useState<MachineNode | null>(null);

  const fetchFleet = async (): Promise<void> => {
    setIsLoading(true);
    try {
      const data = await MachinesService.listMachines();
      setMachines(data);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchFleet();
  }, []);

  const getStatusBadge = (status: MachineStatus): { label: string; style: string } => {
    switch (status) {
      case 'online':
        return { label: t('statusOnline'), style: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300' };
      case 'busy':
        return { label: t('statusBusy'), style: 'bg-sky-500/15 border-sky-500/30 text-sky-300' };
      case 'takeover':
        return { label: t('statusTakeover'), style: 'bg-amber-500/15 border-amber-500/40 text-amber-300 animate-pulse' };
      case 'offline':
      default:
        return { label: t('statusOffline'), style: 'bg-slate-800 border-slate-700 text-slate-400' };
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Action Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-5 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2.5">
            <Server className="w-5 h-5 text-indigo-400" />
            <span>{t('title')}</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">{t('subtitle')}</p>
        </div>

        <div className="flex items-center gap-2.5 self-end sm:self-auto">
          <button
            type="button"
            onClick={fetchFleet}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-300 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
            <span>{t('refreshBtn')}</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setIsConnectModalOpen(true);
            }}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow-lg shadow-indigo-600/20 transition-all active:scale-[0.98]"
          >
            <Plus className="w-4 h-4" />
            <span>{t('connectBtn')}</span>
          </button>
        </div>
      </div>

      {/* Grid of Nodes */}
      {machines.length === 0 ? (
        <div className="text-center py-16 px-4 rounded-2xl bg-slate-950/40 border border-slate-800/80">
          <Server className="w-10 h-10 mx-auto text-slate-600 mb-3" />
          <p className="text-xs text-slate-400 max-w-sm mx-auto mb-4">{t('emptyCluster')}</p>
          <button
            type="button"
            onClick={() => {
              setIsConnectModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>{t('connectBtn')}</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {machines.map((node) => {
            const statusBadge = getStatusBadge(node.status);

            return (
              <div
                key={node.machine_id}
                className="p-5 rounded-2xl bg-slate-900 border border-slate-800 hover:border-slate-700/80 transition-all flex flex-col justify-between space-y-4 shadow-sm"
              >
                {/* Node Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 text-indigo-400">
                      <Laptop className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                        {node.display_name}
                      </h3>
                      <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono mt-0.5">
                        <span>{node.hostname}</span>
                        <span>•</span>
                        <span>{node.ip_address}</span>
                      </div>
                    </div>
                  </div>

                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${statusBadge.style}`}
                  >
                    {statusBadge.label}
                  </span>
                </div>

                {/* Real-time Telemetry Metrics */}
                <div className="grid grid-cols-3 gap-2.5 p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-xs">
                  <div>
                    <span className="text-[10px] text-slate-500 flex items-center gap-1 mb-1">
                      <Cpu className="w-3 h-3 text-sky-400" />
                      {t('cpuUsage')}
                    </span>
                    <span className="font-mono font-semibold text-slate-200">
                      {node.metrics.cpu_usage_pct.toFixed(1)}%
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-500 flex items-center gap-1 mb-1">
                      <Activity className="w-3 h-3 text-indigo-400" />
                      {t('memUsage')}
                    </span>
                    <span className="font-mono font-semibold text-slate-200">
                      {node.metrics.memory_usage_pct.toFixed(1)}%
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-500 flex items-center gap-1 mb-1">
                      <HardDrive className="w-3 h-3 text-purple-400" />
                      {t('diskUsage')}
                    </span>
                    <span className="font-mono font-semibold text-slate-200">
                      {node.metrics.disk_usage_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Footer & Live Takeover Button */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
                  <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
                    <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />
                    <span>
                      {t('activeTasks')}: <strong className="text-slate-200">{node.metrics.active_tasks_count}</strong>
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setSelectedMachineForTakeover(node);
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 text-indigo-300 text-xs font-medium transition-all"
                  >
                    <Tv className="w-3.5 h-3.5" />
                    <span>{t('liveScreen')}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Connect Machine Modal */}
      <ConnectMachineModal
        isOpen={isConnectModalOpen}
        onClose={() => {
          setIsConnectModalOpen(false);
        }}
        onConnectedSuccess={() => {
          fetchFleet();
        }}
      />

      {/* Live Takeover Drawer */}
      <LiveTakeoverDrawer
        isOpen={selectedMachineForTakeover !== null}
        machine={selectedMachineForTakeover}
        onClose={() => {
          setSelectedMachineForTakeover(null);
        }}
        onStatusChange={() => {
          fetchFleet();
        }}
      />
    </div>
  );
};
