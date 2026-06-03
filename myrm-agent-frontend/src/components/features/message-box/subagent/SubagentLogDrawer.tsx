import React, { useEffect, useRef } from 'react';
import { SubagentLog } from '@/store/useSubagentStore';

interface Props {
  logs: SubagentLog[];
}

export const SubagentLogDrawer: React.FC<Props> = ({ logs }) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs.length]);

  return (
    <div className="p-3 max-h-[300px] overflow-y-auto font-mono text-xs">
      {logs.length === 0 ? (
        <div className="text-zinc-500 italic text-center py-4">No logs available yet...</div>
      ) : (
        <div className="space-y-1.5">
          {logs.map((log) => (
            <div key={log.id} className="flex items-start gap-2">
              <span className="text-zinc-400 shrink-0 select-none">
                [{new Date(log.timestamp).toLocaleTimeString()}]
              </span>
              <span
                className={`shrink-0 font-bold ${
                  log.level === 'ERROR' ? 'text-red-500' : log.level === 'WARNING' ? 'text-yellow-500' : 'text-blue-500'
                }`}
              >
                {log.level}
              </span>
              {log.toolName && <span className="text-purple-500 shrink-0">[{log.toolName}]</span>}
              <span className="text-zinc-800 dark:text-zinc-300 break-words flex-1 leading-relaxed">
                {log.message}
                {log.error && <span className="text-red-500 ml-2 block mt-1">Error: {log.error}</span>}
              </span>
              {log.durationMs !== undefined && <span className="text-zinc-400 shrink-0 ml-2">{log.durationMs}ms</span>}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}
    </div>
  );
};
