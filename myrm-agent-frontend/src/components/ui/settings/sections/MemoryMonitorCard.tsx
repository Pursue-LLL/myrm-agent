'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { IconActivity, IconAlertTriangle, IconCpu, IconPlay, IconSquare } from '@/components/ui/icons/PremiumIcons';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { toast } from '@/lib/utils/toast';

interface MemoryMetric {
  cpu_percent: number;
  memory_mb: number;
  vms_mb: number;
  python_gc_objects: number;
  native_mb_estimate: number;
  timestamp: number;
}

interface TopAllocation {
  file: string;
  line: number;
  size_kb: number;
  count: number;
}

export const MemoryMonitorCard = memo(() => {
  const [history, setHistory] = useState<MemoryMetric[]>([]);
  const [isProfiling, setIsProfiling] = useState(false);
  const [topAllocations, setTopAllocations] = useState<TopAllocation[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/health/memory/history');
      if (res.ok) {
        const data = await res.json();
        setHistory(data.history || []);
      }
    } catch (err) {
      console.error('Failed to fetch memory history', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
    const handleSseEvent = (e: any) => {
      if (e.detail?.history) {
        setHistory(e.detail.history);
      }
    };
    window.addEventListener('memory_history_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('memory_history_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
    };
  }, [fetchHistory]);

  const handleStartProfiling = async () => {
    try {
      const res = await fetch('/api/v1/health/memory/profile/start', { method: 'POST' });
      if (res.ok) {
        setIsProfiling(true);
        setTopAllocations([]);
        toast.success('Heap profiling started. System may experience slight overhead.');
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to start profiling');
      }
    } catch (err) {
      console.error(err);
      toast.error('Network error starting profiling');
    }
  };

  const handleStopProfiling = async () => {
    try {
      const res = await fetch('/api/v1/health/memory/profile/stop', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setIsProfiling(false);
        setTopAllocations(data.top_allocations || []);
        toast.success('Heap profiling stopped. Results ready.');
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to stop profiling');
      }
    } catch (err) {
      console.error(err);
      toast.error('Network error stopping profiling');
    }
  };

  const formatTime = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between px-2">
        <div className="flex items-center gap-3">
          <IconActivity className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">Memory & Profiling</h2>
        </div>
        <div className="flex items-center gap-2">
          {isProfiling ? (
            <button
              onClick={handleStopProfiling}
              className="flex items-center gap-2 px-3 py-1.5 bg-red-500/20 text-red-500 hover:bg-red-500/30 rounded-lg text-xs font-bold transition-colors"
            >
              <IconSquare className="w-3.5 h-3.5 fill-current" />
              Stop Profiling
            </button>
          ) : (
            <button
              onClick={handleStartProfiling}
              className="flex items-center gap-2 px-3 py-1.5 bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/30 rounded-lg text-xs font-bold transition-colors"
            >
              <IconPlay className="w-3.5 h-3.5 fill-current" />
              Start Heap Profiling
            </button>
          )}
        </div>
      </div>

      <div className="p-6 rounded-[2.5rem] bg-white/5 border border-white/10 space-y-6">
        {/* Chart Area */}
        <div className="h-64 w-full">
          {loading && history.length === 0 ? (
            <div className="w-full h-full flex items-center justify-center text-muted-foreground animate-pulse">
              Loading memory history...
            </div>
          ) : history.length === 0 ? (
            <div className="w-full h-full flex items-center justify-center text-muted-foreground">
              No memory history available.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorPython" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorNative" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={formatTime}
                  stroke="rgba(255,255,255,0.3)"
                  fontSize={10}
                  tickMargin={10}
                />
                <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} tickFormatter={(val) => `${val}MB`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '12px',
                    fontSize: '12px',
                  }}
                  labelFormatter={(val) => formatTime(val as number)}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
                <Area
                  type="monotone"
                  dataKey="memory_mb"
                  name="Total RSS (MB)"
                  stroke="#818cf8"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorPython)"
                />
                <Area
                  type="monotone"
                  dataKey="native_mb_estimate"
                  name="Native Estimate (MB)"
                  stroke="#34d399"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorNative)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Profiling Warning */}
        {isProfiling && (
          <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
            <IconAlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0 animate-pulse" />
            <div>
              <p className="text-xs font-bold text-amber-500 mb-1">Heap Profiling is Active</p>
              <p className="text-xs text-amber-500/80 leading-relaxed">
                The system is currently tracking all Python memory allocations. This may cause a 10-20% performance
                overhead. Click Stop Profiling to view the results.
              </p>
            </div>
          </div>
        )}

        {/* Top Allocations Table */}
        {!isProfiling && topAllocations.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-bold text-foreground">
              <IconCpu className="w-4 h-4 text-indigo-400" />
              Top Memory Allocations
            </div>
            <div className="overflow-x-auto rounded-xl border border-white/10 bg-black/20">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/5 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">File</th>
                    <th className="px-4 py-3 font-medium">Line</th>
                    <th className="px-4 py-3 font-medium text-right">Size (KB)</th>
                    <th className="px-4 py-3 font-medium text-right">Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {topAllocations.map((alloc, i) => {
                    const fileName = alloc.file.split('/').pop() || alloc.file;
                    return (
                      <tr key={i} className="hover:bg-white/5 transition-colors">
                        <td className="px-4 py-3 text-indigo-300 font-mono truncate max-w-[200px]" title={alloc.file}>
                          {fileName}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{alloc.line}</td>
                        <td className="px-4 py-3 text-right font-mono text-emerald-400">{alloc.size_kb.toFixed(1)}</td>
                        <td className="px-4 py-3 text-right text-muted-foreground">{alloc.count}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
});

MemoryMonitorCard.displayName = 'MemoryMonitorCard';
export default MemoryMonitorCard;
