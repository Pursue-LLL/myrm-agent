'use client';

import { GlobalSkillQualityDashboard } from './GlobalSkillQualityDashboard';

/**
 * Skill Quality Settings Section
 *
 * Displays global skill quality metrics and aggregated analytics.
 * Integrates with the GlobalSkillQualityDashboard component for
 * real-time quality monitoring.
 */
export function SkillQualitySection() {
  return (
    <div className="w-full max-w-5xl">
      <GlobalSkillQualityDashboard />
    </div>
  );
}

export default SkillQualitySection;
