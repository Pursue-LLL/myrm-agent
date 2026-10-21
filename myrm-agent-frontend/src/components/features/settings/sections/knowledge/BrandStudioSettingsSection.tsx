'use client';

import { memo } from 'react';
import BrandStudioSection from '@/components/features/brand-studio/BrandStudioSection';

const BrandStudioSettingsSection = memo(() => (
  <div className="p-6 lg:p-8">
    <BrandStudioSection />
  </div>
));

BrandStudioSettingsSection.displayName = 'BrandStudioSettingsSection';

export default BrandStudioSettingsSection;
