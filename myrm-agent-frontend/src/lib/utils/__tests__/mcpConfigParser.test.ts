/**
 * MCP配置解析器单元测试
 */

import { describe, it, expect } from 'vitest';
import { parseServerConfig, parseMCPConfigsFromJSON } from '../mcpConfigParser';

describe('parseServerConfig', () => {
  it('应该解析SSE类型的配置', () => {
    const result = parseServerConfig('test-server', {
      type: 'sse',
      url: 'http://example.com/sse',
      description: 'Test SSE server',
    });

    expect(result).toEqual({
      name: 'test-server',
      type: 'sse',
      url: 'http://example.com/sse',
      command: null,
      args: null,
      description: 'Test SSE server',
      enabled: true,
      headers: null,
      hostSerial: false,
      keepaliveInterval: null,
      extra_params: {},
    });
  });

  it('应该解析STDIO类型的配置', () => {
    const result = parseServerConfig('cli-server', {
      command: 'npx',
      args: ['-y', 'mcp-server'],
      description: 'CLI server',
    });

    expect(result).toEqual({
      name: 'cli-server',
      type: 'stdio',
      url: null,
      command: 'npx',
      args: ['-y', 'mcp-server'],
      description: 'CLI server',
      enabled: true,
      headers: null,
      hostSerial: false,
      keepaliveInterval: null,
      extra_params: {},
    });
  });

  it('应该处理额外参数（env, cwd, headers）', () => {
    const result = parseServerConfig('advanced-server', {
      type: 'sse',
      url: 'http://example.com',
      env: { API_KEY: 'secret' },
      cwd: '/path/to/dir',
      headers: { Authorization: 'Bearer token' },
    });

    expect(result.extra_params).toEqual({
      env: { API_KEY: 'secret' },
      cwd: '/path/to/dir',
    });
    expect(result.headers).toEqual({ Authorization: 'Bearer token' });
  });

  it('应该在name为空时抛出错误', () => {
    expect(() => parseServerConfig('', {})).toThrow('Server name cannot be empty');
    expect(() => parseServerConfig('   ', {})).toThrow('Server name cannot be empty');
  });

  it('缺少description时应保持为空串', () => {
    const result = parseServerConfig('my-server', {
      type: 'sse',
      url: 'http://example.com',
    });

    expect(result.description).toBe('');
  });

  it('应该解析 TLS/mTLS 字段（snake_case）', () => {
    const result = parseServerConfig('tls-server', {
      type: 'streamable_http',
      url: 'https://example.com/mcp',
      ssl_verify: '/etc/ca.pem',
      client_cert: '/etc/client.pem',
      client_key: '/etc/client-key.pem',
      client_key_password: 's3cr3t',
    });

    expect(result.sslVerify).toBe('/etc/ca.pem');
    expect(result.clientCert).toBe('/etc/client.pem');
    expect(result.clientKey).toBe('/etc/client-key.pem');
    expect(result.clientKeyPassword).toBe('s3cr3t');
  });

  it('应该解析 TLS/mTLS 字段（camelCase）', () => {
    const result = parseServerConfig('tls-server', {
      type: 'sse',
      url: 'https://example.com/sse',
      sslVerify: false,
      clientCert: '/etc/client.pem',
      clientKeyPassword: 'pw',
    });

    expect(result.sslVerify).toBe(false);
    expect(result.clientCert).toBe('/etc/client.pem');
    expect(result.clientKeyPassword).toBe('pw');
  });

  it('应该解析 host_serial / hostSerial 字段', () => {
    const snake = parseServerConfig('host-serial-snake', {
      type: 'sse',
      url: 'https://example.com/sse',
      host_serial: true,
    });
    expect(snake.hostSerial).toBe(true);

    const camel = parseServerConfig('host-serial-camel', {
      type: 'sse',
      url: 'https://example.com/sse',
      hostSerial: false,
    });
    expect(camel.hostSerial).toBe(false);
  });

  it('应该解析 keepalive_interval / keepaliveInterval 字段', () => {
    const snake = parseServerConfig('keepalive-snake', {
      type: 'sse',
      url: 'https://example.com/sse',
      keepalive_interval: 45,
    });
    expect(snake.keepaliveInterval).toBe(45);

    const camel = parseServerConfig('keepalive-camel', {
      type: 'sse',
      url: 'https://example.com/sse',
      keepaliveInterval: 30,
    });
    expect(camel.keepaliveInterval).toBe(30);

    const invalid = parseServerConfig('keepalive-invalid', {
      type: 'sse',
      url: 'https://example.com/sse',
      keepalive_interval: 1,
    });
    expect(invalid.keepaliveInterval).toBeNull();

    const stdioIgnored = parseServerConfig('keepalive-stdio', {
      command: 'python',
      args: ['-m', 'stateful_mcp'],
      keepalive_interval: 30,
    });
    expect(stdioIgnored.keepaliveInterval).toBeNull();
  });

  it('应该将 http transport 别名归一化为 streamable_http', () => {
    const httpType = parseServerConfig('http-type', {
      type: 'http',
      url: 'https://example.com/mcp',
      keepaliveInterval: 15,
    });
    expect(httpType.type).toBe('streamable_http');
    expect(httpType.keepaliveInterval).toBe(15);

    const transportAlias = parseServerConfig('http-transport', {
      transport: 'streamable-http',
      url: 'https://example.com/mcp',
      keepalive_interval: 20,
    });
    expect(transportAlias.type).toBe('streamable_http');
    expect(transportAlias.keepaliveInterval).toBe(20);
  });

  it('未提供 TLS 字段时不应设置', () => {
    const result = parseServerConfig('plain', {
      type: 'sse',
      url: 'https://example.com',
    });

    expect(result.sslVerify).toBeUndefined();
    expect(result.clientCert).toBeUndefined();
    expect(result.clientKeyPassword).toBeUndefined();
  });
});

describe('parseMCPConfigsFromJSON', () => {
  it('应该解析单个配置对象', () => {
    const json = JSON.stringify({
      name: 'test-server',
      type: 'sse',
      url: 'http://example.com',
      description: 'Test server',
    });

    const result = parseMCPConfigsFromJSON(json);

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('test-server');
    expect(result[0].type).toBe('sse');
  });

  it('应该解析mcpServers包裹格式', () => {
    const json = JSON.stringify({
      mcpServers: {
        'server-1': { type: 'sse', url: 'http://s1.com' },
        'server-2': { command: 'npx', args: ['mcp'] },
      },
    });

    const result = parseMCPConfigsFromJSON(json);

    expect(result).toHaveLength(2);
    expect(result.find((c) => c.name === 'server-1')).toBeDefined();
    expect(result.find((c) => c.name === 'server-2')).toBeDefined();
  });

  it('应该解析数组格式', () => {
    const json = JSON.stringify([
      { name: 's1', type: 'sse', url: 'http://s1.com' },
      { name: 's2', command: 'npx', args: ['mcp'] },
    ]);

    const result = parseMCPConfigsFromJSON(json);

    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('s1');
    expect(result[1].name).toBe('s2');
  });

  it('应该在输入为空时抛出错误', () => {
    expect(() => parseMCPConfigsFromJSON('')).toThrow('JSON text cannot be empty');
    expect(() => parseMCPConfigsFromJSON('   ')).toThrow('JSON text cannot be empty');
  });

  it('应该在JSON格式无效时抛出错误', () => {
    expect(() => parseMCPConfigsFromJSON('{')).toThrow('Invalid JSON format');
    expect(() => parseMCPConfigsFromJSON('not json')).toThrow('Invalid JSON format');
  });

  it('应该在JSON为null时抛出错误', () => {
    expect(() => parseMCPConfigsFromJSON('null')).toThrow('Parsed JSON cannot be null');
  });

  it('应该跳过无效的配置但继续处理其他配置', () => {
    const json = JSON.stringify({
      mcpServers: {
        '': { type: 'sse', url: 'http://invalid.com' }, // 无效：空name
        'valid-server': { type: 'sse', url: 'http://valid.com' }, // 有效
      },
    });

    const result = parseMCPConfigsFromJSON(json);

    // 应该只返回有效的配置
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('valid-server');
  });

  it('应该处理空数组', () => {
    const json = JSON.stringify([]);
    const result = parseMCPConfigsFromJSON(json);
    expect(result).toHaveLength(0);
  });

  it('应该处理空对象', () => {
    const json = JSON.stringify({});
    const result = parseMCPConfigsFromJSON(json);
    expect(result).toHaveLength(0);
  });
});
