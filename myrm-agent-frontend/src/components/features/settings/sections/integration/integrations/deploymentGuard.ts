export interface LocalOnlySandboxGuardInput {
  isSandboxMode: boolean;
  isLocalTauriOnlyEntry: boolean;
}

export interface CloudLoopbackGuardInput {
  status: string;
  isSandboxMode: LocalOnlySandboxGuardInput['isSandboxMode'];
  isLocalTauriOnlyEntry: LocalOnlySandboxGuardInput['isLocalTauriOnlyEntry'];
}

export function shouldBlockLocalOnlyInSandbox(input: LocalOnlySandboxGuardInput): boolean {
  return input.isSandboxMode && input.isLocalTauriOnlyEntry;
}

export function shouldBlockCloudLoopbackConnect(input: CloudLoopbackGuardInput): boolean {
  return (
    input.status === 'cloud_not_supported' &&
    shouldBlockLocalOnlyInSandbox(input)
  );
}
