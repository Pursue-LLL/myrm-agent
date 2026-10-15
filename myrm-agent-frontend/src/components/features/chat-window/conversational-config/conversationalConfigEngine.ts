import {
  ConfigParamItem,
  ConversationalConfigIntent,
} from './conversationalConfigTypes';

/**
 * 敏感秘钥脱敏展示函数 (保留前4位与后4位，中间隐藏)
 */
export function maskSecretKey(key: string): string {
  const trimmed = key.trim();
  if (trimmed.length <= 8) {
    return '********';
  }
  const prefix = trimmed.slice(0, 4);
  const suffix = trimmed.slice(-4);
  return `${prefix}****${suffix}`;
}

let intentCounter = 0;

/**
 * 自然语言驱动的系统配置意图理解器
 */
export function parseNaturalLanguageConfigIntent(
  utterance: string,
): ConversationalConfigIntent | null {
  const text = utterance.trim().toLowerCase();
  if (!text) {
    return null;
  }

  intentCounter += 1;
  const id = `config-intent-${Date.now()}-${intentCounter}`;

  // 1. 模型切换意图
  if (
    text.includes('模型') &&
    (text.includes('换成') ||
      text.includes('切成') ||
      text.includes('切换') ||
      text.includes('设为') ||
      text.includes('改为') ||
      text.includes('默认'))
  ) {
    let targetModel = 'claude-3-7-sonnet';
    if (text.includes('deepseek') || text.includes('深度求索')) {
      targetModel = 'deepseek-v3';
    } else if (text.includes('gpt-4o') || text.includes('gpt4o')) {
      targetModel = 'gpt-4o';
    } else if (text.includes('claude')) {
      targetModel = 'claude-3-7-sonnet';
    } else if (text.includes('qwen') || text.includes('千问')) {
      targetModel = 'qwen-2.5-72b';
    }

    return {
      id,
      category: 'model_switch',
      title: '主模型切换配置确认',
      description: `系统已识别到您希望将主模型切换为 ${targetModel}，请确认并应用。`,
      matchedUtterance: utterance,
      isApplied: false,
      createdAt: Date.now(),
      params: [
        {
          key: 'model_name',
          label: '目标模型标识',
          type: 'select',
          value: targetModel,
          options: [
            'claude-3-7-sonnet',
            'deepseek-v3',
            'gpt-4o',
            'qwen-2.5-72b',
          ],
        },
        {
          key: 'enable_thinking',
          label: '启用深度思考推理链',
          type: 'select',
          value: 'true',
          options: ['true', 'false'],
        },
      ],
    };
  }

  // 2. API Key / 凭据录入意图
  if (
    text.includes('key') ||
    text.includes('token') ||
    text.includes('密钥') ||
    text.includes('凭据')
  ) {
    let provider = 'OpenAI';
    if (text.includes('anthropic') || text.includes('claude')) {
      provider = 'Anthropic';
    } else if (text.includes('deepseek')) {
      provider = 'DeepSeek';
    } else if (text.includes('volcengine') || text.includes('火山')) {
      provider = 'Volcengine';
    }

    return {
      id,
      category: 'api_key_entry',
      title: `${provider} 接口凭据安全写入确认`,
      description: `系统检测到凭据配置意图，请输入脱敏后的 API Key，只有点击确认后才会安全存入沙箱密钥库。`,
      matchedUtterance: utterance,
      isApplied: false,
      createdAt: Date.now(),
      params: [
        {
          key: 'provider',
          label: '服务供应商',
          type: 'text',
          value: provider,
        },
        {
          key: 'api_key',
          label: 'API 授权凭据',
          type: 'password',
          value: '',
          placeholder: 'sk-... 格式密钥',
          isSecret: true,
        },
      ],
    };
  }

  // 3. 搜索引擎切换意图
  if (
    text.includes('搜索') &&
    (text.includes('换成') || text.includes('切') || text.includes('用'))
  ) {
    let engine = 'tavily';
    if (text.includes('bing') || text.includes('必应')) {
      engine = 'bing';
    } else if (text.includes('google') || text.includes('谷歌')) {
      engine = 'google';
    } else if (text.includes('duckduckgo')) {
      engine = 'duckduckgo';
    }

    return {
      id,
      category: 'search_engine',
      title: '联网搜索引擎切换确认',
      description: `已识别搜索引擎切换指令，目标引擎为 ${engine}。`,
      matchedUtterance: utterance,
      isApplied: false,
      createdAt: Date.now(),
      params: [
        {
          key: 'search_engine',
          label: '联网搜索内核',
          type: 'select',
          value: engine,
          options: ['tavily', 'bing', 'google', 'duckduckgo'],
        },
      ],
    };
  }

  // 4. 协同渠道绑定意图
  if (
    text.includes('绑定') ||
    text.includes('连上') ||
    text.includes('接入')
  ) {
    let channel = 'feishu';
    if (text.includes('钉钉') || text.includes('dingtalk')) {
      channel = 'dingtalk';
    } else if (text.includes('telegram') || text.includes('tg')) {
      channel = 'telegram';
    } else if (text.includes('slack')) {
      channel = 'slack';
    }

    return {
      id,
      category: 'channel_binding',
      title: '多端协作机器人通道绑定',
      description: `准备接入 ${channel} 消息网关，请核验机器人 Webhook 或 AppID。`,
      matchedUtterance: utterance,
      isApplied: false,
      createdAt: Date.now(),
      params: [
        {
          key: 'channel_type',
          label: '协作平台',
          type: 'text',
          value: channel,
        },
        {
          key: 'webhook_url',
          label: 'Webhook 回调网关',
          type: 'password',
          value: '',
          placeholder: 'https://open.feishu.cn/open-apis/...',
          isSecret: true,
        },
      ],
    };
  }

  return null;
}

/**
 * 校验配置卡片参数是否齐备
 */
export function validateConfigParams(params: ConfigParamItem[]): {
  valid: boolean;
  errorMessage?: string;
} {
  for (const p of params) {
    if (p.isSecret && !p.value.trim()) {
      return {
        valid: false,
        errorMessage: `请先填写「${p.label}」，再进行授权应用。`,
      };
    }
  }
  return { valid: true };
}
