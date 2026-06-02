import React from 'react';
import useCompanionStore from '@/store/useCompanionStore';

interface DagNode {
  id: string;
  data: {
    label: string;
    status: 'pending' | 'in_progress' | 'completed' | 'failed';
    expected_output?: string;
    risk_level?: string;
  };
}

interface DagEdge {
  id: string;
  source: string;
  target: string;
}

interface DagData {
  nodes: DagNode[];
  edges: DagEdge[];
}

interface GoalDagRendererProps {
  sessionId: string;
}

export const GoalDagRenderer: React.FC<GoalDagRendererProps> = ({ sessionId: _sessionId }) => {
  const dagData = useCompanionStore((state) => state.dagData) as unknown as DagData | null;

  if (!dagData || dagData.nodes.length === 0) {
    return (
      <div className="p-4 bg-gray-900 rounded-lg border border-gray-800 text-gray-500 text-sm italic text-center">
        Waiting for DAG plan generation...
      </div>
    );
  }

  return (
    <div className="p-6 bg-gray-900 rounded-xl border border-gray-800 shadow-2xl relative overflow-hidden">
      <h3 className="text-lg font-bold text-gray-100 mb-4 tracking-wide">Execution DAG</h3>

      <div className="flex flex-col space-y-4 relative z-10">
        {dagData.nodes.map((node) => {
          let statusColor = 'bg-gray-800 border-gray-700 text-gray-400';
          let pulse = '';

          if (node.data.status === 'completed') {
            statusColor = 'bg-emerald-900/30 border-emerald-500/50 text-emerald-400';
          } else if (node.data.status === 'in_progress') {
            statusColor = 'bg-indigo-900/30 border-indigo-500/50 text-indigo-400';
            pulse = 'animate-pulse shadow-[0_0_15px_rgba(99,102,241,0.5)]';
          } else if (node.data.status === 'failed') {
            statusColor = 'bg-red-900/30 border-red-500/50 text-red-400';
          }

          return (
            <div
              key={node.id}
              className={`p-4 rounded-lg border ${statusColor} ${pulse} transition-all duration-500 ease-in-out transform hover:scale-[1.02]`}
            >
              <div className="flex justify-between items-center mb-2">
                <span className="font-mono text-xs opacity-70 uppercase tracking-widest">{node.id}</span>
                <span className="text-xs font-bold uppercase tracking-wider px-2 py-1 rounded-full bg-black/20">
                  {node.data.status}
                </span>
              </div>
              <p className="text-sm font-medium leading-relaxed">{node.data.label}</p>

              {node.data.expected_output && (
                <div className="mt-3 text-xs opacity-75 border-t border-current/20 pt-2">
                  <span className="font-semibold">Expected:</span> {node.data.expected_output}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Decorative background elements */}
      <div className="absolute top-0 right-0 -mt-10 -mr-10 w-40 h-40 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-0 left-0 -mb-10 -ml-10 w-40 h-40 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>
    </div>
  );
};
