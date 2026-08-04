import { describe, expect, it, vi } from 'vitest';

import {
  TUNNEL_AGENT_IMAGE,
  buildTunnelDockerBuildCommand,
  buildTunnelDockerRunCommand,
} from '@/lib/tunnel-deploy';

describe('buildTunnelDockerBuildCommand', () => {
  it('builds docker build with pinned image tag', () => {
    expect(buildTunnelDockerBuildCommand()).toBe(`docker build -t ${TUNNEL_AGENT_IMAGE} .`);
  });
});

describe('buildTunnelDockerRunCommand', () => {
  it('builds docker run with relay url and tunnel params', () => {
    vi.stubEnv('NEXT_PUBLIC_CP_BASE_URL', 'https://cp.example.com');

    const cmd = buildTunnelDockerRunCommand({
      tunnelId: 'abc123',
      upstreamUrl: 'http://10.0.1.50:8080/mcp',
      authToken: 'secret-token',
    });

    expect(cmd).toContain('docker run --rm -d');
    expect(cmd).toContain('--add-host=host.docker.internal:host-gateway');
    expect(cmd).toContain('--name myrm-tunnel-abc123');
    expect(cmd).toContain('myrm/tunnel-agent:0.1.0');
    expect(cmd).toContain('--relay-url https://cp.example.com');
    expect(cmd).toContain('--tunnel-id abc123');
    expect(cmd).toContain("--token 'secret-token'");
    expect(cmd).toContain('--upstream http://10.0.1.50:8080/mcp');
  });
});
