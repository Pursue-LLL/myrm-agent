import { resolveCpBaseUrl } from '@/lib/cp-base-url';

export interface TunnelDeployParams {
  tunnelId: string;
  upstreamUrl: string;
  authToken: string;
}

export const TUNNEL_AGENT_IMAGE = 'myrm/tunnel-agent:0.1.0';

/** Build image locally from clients/myrm-tunnel-agent/ (enterprise deployment package). */
export function buildTunnelDockerBuildCommand(): string {
  return `docker build -t ${TUNNEL_AGENT_IMAGE} .`;
}

export function buildTunnelDockerRunCommand(params: TunnelDeployParams): string {
  const relayUrl = resolveCpBaseUrl();
  const containerName = `myrm-tunnel-${params.tunnelId}`;

  return [
    'docker run --rm -d \\',
    '  --add-host=host.docker.internal:host-gateway \\',
    `  --name ${containerName} \\`,
    `  ${TUNNEL_AGENT_IMAGE} \\`,
    `  --relay-url ${relayUrl} \\`,
    `  --tunnel-id ${params.tunnelId} \\`,
    `  --token '${params.authToken}' \\`,
    `  --upstream ${params.upstreamUrl}`,
  ].join('\n');
}
