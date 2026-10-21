'use client';

import { memo } from 'react';
import ThemeStudioSection from '@/components/features/theme-studio/ThemeStudioSection';

const ThemeStudioSettingsSection = memo(() => (
  <div className="p-6 lg:p-8">
    <ThemeStudioSection />
  </div>
));

ThemeStudioSettingsSection.displayName = 'ThemeStudioSettingsSection';

export default ThemeStudioSettingsSection;
