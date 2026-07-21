import { MCPServiceConfig } from '@/store/useConfigStore';

/**
 * 解析单个MCP服务器配置对象
 * @param name 服务器名称
 * @param config 配置对象
 * @returns 标准化的MCPServiceConfig
 * @throws {Error} 当name为空时抛出错误
 */
export function parseServerConfig(name: string, config: Record<string, unknown>): MCPServiceConfig {
  // 边缘场景处理：验证name
  if (!name || typeof name !== 'string' || name.trim() === '') {
    throw new Error('Server name cannot be empty');
  }

  // 判断连接类型
  let type: 'sse' | 'stdio' | 'streamable_http' = 'stdio';

  if (config.type === 'sse') {
    type = 'sse';
  } else if (config.type === 'streamableHttp' || config.type === 'streamable_http') {
    type = 'streamable_http';
  } else if (config.command) {
    type = 'stdio';
  } else if (config.url) {
    type = 'sse';
  }

  const rawHeaders = config.headers as Record<string, string> | undefined;
  const rawHostSerial = config.host_serial ?? config.hostSerial;
  const rawKeepaliveInterval = config.keepalive_interval ?? config.keepaliveInterval;

  const result: MCPServiceConfig = {
    name,
    type,
    url: (config.url as string) || null,
    command: (config.command as string) || null,
    args: Array.isArray(config.args) ? config.args.map(String) : null,
    description: (config.description as string) || '',
    enabled: true,
    headers: rawHeaders && Object.keys(rawHeaders).length > 0 ? rawHeaders : null,
    hostSerial: typeof rawHostSerial === 'boolean' ? rawHostSerial : false,
    keepaliveInterval:
      typeof rawKeepaliveInterval === 'number' && Number.isFinite(rawKeepaliveInterval) && rawKeepaliveInterval >= 5
        ? rawKeepaliveInterval
        : null,
    extra_params: {
      ...(config.env ? { env: config.env as Record<string, string> } : {}),
      ...(config.cwd ? { cwd: config.cwd as string } : {}),
    },
  };

  if (config.ssl_verify !== undefined || config.sslVerify !== undefined) {
    const raw = config.ssl_verify ?? config.sslVerify;
    result.sslVerify = typeof raw === 'boolean' || typeof raw === 'string' ? raw : null;
  }
  if (config.client_cert || config.clientCert) {
    result.clientCert = (config.client_cert as string) || (config.clientCert as string) || null;
  }
  if (config.client_key || config.clientKey) {
    result.clientKey = (config.client_key as string) || (config.clientKey as string) || null;
  }
  if (config.client_key_password || config.clientKeyPassword) {
    result.clientKeyPassword = (config.client_key_password as string) || (config.clientKeyPassword as string) || null;
  }

  return result;
}

/**
 * 从JSON字符串解析MCP配置列表
 * 支持多种格式：
 * - 单个配置对象: { "name": "...", "type": "sse", "url": "..." }
 * - mcpServers包裹: { "mcpServers": { "server-name": {...} } }
 * - 服务器配置对象: { "server-name": {...}, "another-server": {...} }
 * - 数组格式: [{ "name": "...", ... }]
 *
 * @param jsonText JSON字符串
 * @returns 解析后的配置数组
 * @throws {Error} JSON解析错误、格式不支持或数据无效
 */
export function parseMCPConfigsFromJSON(jsonText: string): MCPServiceConfig[] {
  // 边缘场景处理：验证输入
  if (!jsonText || typeof jsonText !== 'string' || jsonText.trim() === '') {
    throw new Error('JSON text cannot be empty');
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch (error) {
    throw new Error(`Invalid JSON format: ${error instanceof Error ? error.message : 'Parse failed'}`);
  }

  // 边缘场景处理：验证parsed不为null
  if (parsed === null || parsed === undefined) {
    throw new Error('Parsed JSON cannot be null or undefined');
  }

  const importedConfigs: MCPServiceConfig[] = [];

  // 格式1: 单个配置对象
  if (typeof parsed === 'object' && !Array.isArray(parsed)) {
    const parsedObj = parsed as Record<string, unknown>;
    if (parsedObj.name && (parsedObj.command || parsedObj.url || parsedObj.type)) {
      importedConfigs.push(parseServerConfig(parsedObj.name as string, parsedObj));
    }
    // 格式2: { "mcpServers": { ... } }
    else if (parsedObj.mcpServers && typeof parsedObj.mcpServers === 'object') {
      const mcpServers = parsedObj.mcpServers as Record<string, unknown>;
      for (const [name, serverConfig] of Object.entries(mcpServers)) {
        const config = serverConfig as Record<string, unknown>;
        try {
          importedConfigs.push(parseServerConfig(name, config));
        } catch (error) {
          // 跳过无效配置但记录错误
          console.warn(`Skipping invalid server config "${name}":`, error);
        }
      }
    }
    // 格式3: 直接是服务器配置对象
    else {
      const parsedObj = parsed as Record<string, unknown>;
      const hasValidServerConfig = Object.values(parsedObj).some(
        (v) => typeof v === 'object' && v !== null && ('command' in v || 'url' in v || 'type' in v),
      );

      if (hasValidServerConfig) {
        for (const [name, serverConfig] of Object.entries(parsedObj)) {
          const config = serverConfig as Record<string, unknown>;
          if (typeof config === 'object' && config !== null) {
            try {
              importedConfigs.push(parseServerConfig(name, config));
            } catch (error) {
              // 跳过无效配置但记录错误
              console.warn(`Skipping invalid server config "${name}":`, error);
            }
          }
        }
      }
    }
  }
  // 格式4: 数组格式
  else if (Array.isArray(parsed)) {
    for (const item of parsed) {
      if (typeof item === 'object' && item !== null && item.name) {
        const config = item as Record<string, unknown>;
        try {
          importedConfigs.push(parseServerConfig(config.name as string, config));
        } catch (error) {
          // 跳过无效配置但记录错误
          console.warn(`Skipping invalid array item "${item.name}":`, error);
        }
      }
    }
  }

  return importedConfigs;
}
