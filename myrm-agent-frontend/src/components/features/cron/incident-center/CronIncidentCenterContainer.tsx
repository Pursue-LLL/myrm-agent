/**
 * Cron Incident Center Container
 * 定时任务事故待办中心整体聚合容器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 行数严格受控在 400 行以内。
 */

import React from 'react';
import { CronIncidentAlertBadge } from './CronIncidentAlertBadge';
import { CronIncidentDrawer } from './CronIncidentDrawer';

export interface CronIncidentCenterContainerProps {
  className?: string;
  showBadge?: boolean;
}

export const CronIncidentCenterContainer: React.FC<CronIncidentCenterContainerProps> = ({
  className = '',
  showBadge = true,
}) => {
  return (
    <div data-testid="cron-incident-center-container" className={`flex flex-col ${className}`}>
      {showBadge && <CronIncidentAlertBadge />}
      <CronIncidentDrawer />
    </div>
  );
};
