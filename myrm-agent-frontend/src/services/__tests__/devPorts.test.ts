import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../api';
import {
  listDevPorts,
  registerDevPort,
  closeDevPort,
  createDevPortTunnel,
  sniffAndRegisterDevPorts,
  type DevPortInfo,
  type DevPortRegisterRequest,
  type DevPortTunnelResponse,
} from '../devPorts';

vi.mock('../api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('devPorts service client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listDevPorts sends GET request to /api/v1/dev-ports', async () => {
    const mockPorts: DevPortInfo[] = [
      {
        port: 3000,
        process_name: 'next-dev',
        pid: 1234,
        protocol: 'http',
        url: 'http://localhost:3000',
        tunnel_url: 'https://preview-3000.sandbox.myrm.io',
        status: 'listening',
        created_at: '2026-10-12T07:00:00Z',
      },
    ];

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockPorts);

    const result = await listDevPorts();

    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/dev-ports');
    expect(result).toEqual(mockPorts);
  });

  it('registerDevPort sends POST request to /api/v1/dev-ports with payload', async () => {
    const request: DevPortRegisterRequest = {
      port: 5173,
      process_name: 'vite',
      protocol: 'http',
    };
    const mockResponse: DevPortInfo = {
      port: 5173,
      process_name: 'vite',
      pid: 5678,
      protocol: 'http',
      url: 'http://localhost:5173',
      tunnel_url: null,
      status: 'listening',
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

    const result = await registerDevPort(request);

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/dev-ports', request);
    expect(result).toEqual(mockResponse);
  });

  it('closeDevPort sends DELETE request to /api/v1/dev-ports/{port}', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ success: true });

    const result = await closeDevPort(3000);

    expect(apiClient.delete).toHaveBeenCalledWith('/api/v1/dev-ports/3000');
    expect(result).toEqual({ success: true });
  });

  it('createDevPortTunnel sends POST request to /api/v1/dev-ports/{port}/tunnel', async () => {
    const mockTunnel: DevPortTunnelResponse = {
      port: 3000,
      tunnel_url: 'https://tunnel-3000.sandbox.myrm.io',
      expires_in_seconds: 3600,
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockTunnel);

    const result = await createDevPortTunnel(3000);

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/dev-ports/3000/tunnel');
    expect(result).toEqual(mockTunnel);
  });

  it('sniffAndRegisterDevPorts sends POST request to /api/v1/dev-ports/sniff with log_text', async () => {
    const rawLogs = 'Ready in 2.1s - Local: http://localhost:3000';
    const mockDiscovered: DevPortInfo[] = [
      {
        port: 3000,
        process_name: 'next',
        pid: null,
        protocol: 'http',
        url: 'http://localhost:3000',
        tunnel_url: null,
        status: 'listening',
        created_at: '2026-10-12T07:00:00Z',
      },
    ];

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockDiscovered);

    const result = await sniffAndRegisterDevPorts(rawLogs);

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/dev-ports/sniff', {
      log_text: rawLogs,
    });
    expect(result).toEqual(mockDiscovered);
  });
});
