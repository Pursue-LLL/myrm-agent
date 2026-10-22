import React from 'react';
import { CollaboratorItem } from './types';

export interface RosterViewProps {
  collaborators: CollaboratorItem[];
}

export const RosterView: React.FC<RosterViewProps> = ({ collaborators }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
      {collaborators.map((c) => (
        <div
          key={c.collaboratorId}
          className="p-2.5 rounded-lg border border-border bg-muted/15 flex flex-col justify-between text-xs"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-semibold text-foreground">{c.name}</span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                c.collaboratorType === 'human'
                  ? 'bg-purple-500/10 text-purple-600 dark:text-purple-400'
                  : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
              }`}
            >
              {c.collaboratorType.toUpperCase()}
            </span>
          </div>
          <p className="text-muted-foreground text-[11px]">{c.roleDescription}</p>
          {c.principalHumanId && (
            <div className="mt-2 text-[10px] text-primary/80 font-mono">
              Principal Owner: {c.principalHumanId}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
