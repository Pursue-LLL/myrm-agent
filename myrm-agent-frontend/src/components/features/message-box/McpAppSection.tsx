'use client';

import React, { memo } from 'react';
import type { McpAppView } from '@/store/chat/types';
import { McpAppViewer } from '@/components/features/artifacts/renderers/McpAppViewer';

interface McpAppSectionProps {
  views: McpAppView[];
}

export const McpAppSection: React.FC<McpAppSectionProps> = memo(({ views }) => {
  return (
    <div className="flex flex-col gap-3 mt-3">
      {views.map((view, idx) => (
        <McpAppViewer key={`${view.serverName}-${view.resourceUri}-${idx}`} view={view} />
      ))}
    </div>
  );
});
McpAppSection.displayName = 'McpAppSection';
