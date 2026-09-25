'use client';

import { memo } from 'react';
import RemoteFirstRunChooser from '@/components/features/settings/sections/system/RemoteFirstRunChooser';
import {
  setOnboardingDeployChoice,
  type OnboardingDeployChoice,
} from '@/lib/onboarding-deploy-choice';

interface DeployChoiceStepProps {
  onComplete: (choice: OnboardingDeployChoice) => void;
}

const DeployChoiceStep = memo(({ onComplete }: DeployChoiceStepProps) => {
  const handleSelect = (choice: OnboardingDeployChoice) => {
    setOnboardingDeployChoice(choice);
    onComplete(choice);
  };

  return (
    <RemoteFirstRunChooser
      onSelectLocal={() => handleSelect('local')}
      onSelectRemote={() => handleSelect('remote')}
      onSelectCloud={() => handleSelect('cloud')}
    />
  );
});

DeployChoiceStep.displayName = 'DeployChoiceStep';
export default DeployChoiceStep;
