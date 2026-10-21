import React from 'react';
import { CollaboratorItem } from './types';

export interface CoAuthoringHeaderProps {
  chatId: string;
  documentId: string;
  collaborators: CollaboratorItem[];
  selectedCollaboratorId: string;
  onSelectCollaborator: (id: string) => void;
}

export const CoAuthoringHeader: React.FC<CoAuthoringHeaderProps> = ({
  chatId,
  documentId,
  collaborators,
  selectedCollaboratorId,
  onSelectCollaborator,
}) => {
  return (
    <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3 mb-3">
      <div>
        <h3 className="text-base font-semibold tracking-tight text-foreground flex items-center gap-2">
          <span>📝 Live Document Tripartite Co-Authoring Ledger</span>
          <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-blue-500/10 text-blue-600 dark:text-blue-400">
            Chat: {chatId}
          </span>
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Doc ID: <span className="font-mono text-foreground">{documentId}</span> | Human-in-the-Loop & Agentic Atomic Lease Sync
        </p>
      </div>

      <fieldset className="flex items-center gap-2 border-none p-0 m-0" aria-label="Collaborator Actor Switcher">
        <label htmlFor="active-collaborator-select" className="text-xs font-medium text-muted-foreground">
          Active Actor:
        </label>
        <select
          id="active-collaborator-select"
          value={selectedCollaboratorId}
          onChange={(e) => onSelectCollaborator(e.target.value)}
          className="text-xs px-2 py-1 bg-background border border-border rounded shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
        >
          {collaborators.map((c) => (
            <option key={c.collaboratorId} value={c.collaboratorId}>
              [{c.collaboratorType.toUpperCase()}] {c.name}
            </option>
          ))}
        </select>
      </fieldset>
    </header>
  );
};
