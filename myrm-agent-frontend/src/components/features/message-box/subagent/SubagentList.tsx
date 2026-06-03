import React from 'react';
import useSubagentStore from '@/store/useSubagentStore';
import { SubagentSummaryCard } from './SubagentSummaryCard';

interface Props {
  messageId: string;
}

export const SubagentList: React.FC<Props> = ({ messageId }) => {
  const taskIds = useSubagentStore((state) => state.messageSubagents[messageId] || []);

  if (!taskIds || taskIds.length === 0) return null;

  return (
    <div className="w-full flex flex-col mt-2 mb-4">
      {taskIds.map((taskId) => (
        <SubagentSummaryCard key={taskId} taskId={taskId} messageId={messageId} />
      ))}
    </div>
  );
};
