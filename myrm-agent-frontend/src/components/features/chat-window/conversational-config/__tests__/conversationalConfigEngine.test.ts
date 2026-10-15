import { describe, expect, it } from 'vitest';
import {
  maskSecretKey,
  parseNaturalLanguageConfigIntent,
  validateConfigParams,
} from '../conversationalConfigEngine';
import { ConfigParamItem } from '../conversationalConfigTypes';

describe('conversationalConfigEngine', () => {
  describe('maskSecretKey', () => {
    it('masks keys with length <= 8 completely', () => {
      expect(maskSecretKey('12345678')).toBe('********');
      expect(maskSecretKey('short')).toBe('********');
    });

    it('masks middle part for keys longer than 8 characters', () => {
      expect(maskSecretKey('sk-ant-api03-abcdefg-1234')).toBe('sk-a****1234');
      expect(maskSecretKey('  sk-test-secret-9999  ')).toBe('sk-t****9999');
    });
  });

  describe('parseNaturalLanguageConfigIntent', () => {
    it('returns null for empty or whitespace utterance', () => {
      expect(parseNaturalLanguageConfigIntent('')).toBeNull();
      expect(parseNaturalLanguageConfigIntent('   ')).toBeNull();
    });

    it('recognizes model switch intents', () => {
      const intentDeepseek = parseNaturalLanguageConfigIntent(
        '把主模型切换成 deepseek 吧',
      );
      expect(intentDeepseek).not.toBeNull();
      expect(intentDeepseek?.category).toBe('model_switch');
      const modelParam = intentDeepseek?.params.find(
        (p) => p.key === 'model_name',
      );
      expect(modelParam?.value).toBe('deepseek-v3');

      const intentGpt = parseNaturalLanguageConfigIntent('请将模型设为 gpt4o');
      expect(intentGpt?.category).toBe('model_switch');
      expect(
        intentGpt?.params.find((p) => p.key === 'model_name')?.value,
      ).toBe('gpt-4o');

      const intentClaude = parseNaturalLanguageConfigIntent(
        '默认模型改用 claude',
      );
      expect(
        intentClaude?.params.find((p) => p.key === 'model_name')?.value,
      ).toBe('claude-3-7-sonnet');

      const intentQwen = parseNaturalLanguageConfigIntent(
        '把模型换成千问 qwen',
      );
      expect(
        intentQwen?.params.find((p) => p.key === 'model_name')?.value,
      ).toBe('qwen-2.5-72b');
    });

    it('recognizes api key entry intents', () => {
      const intentAnthropic = parseNaturalLanguageConfigIntent(
        '我要配置 Anthropic 的 api key 凭据',
      );
      expect(intentAnthropic).not.toBeNull();
      expect(intentAnthropic?.category).toBe('api_key_entry');
      expect(
        intentAnthropic?.params.find((p) => p.key === 'provider')?.value,
      ).toBe('Anthropic');

      const intentDeepSeek = parseNaturalLanguageConfigIntent(
        '输入 deepseek 的密钥 token',
      );
      expect(
        intentDeepSeek?.params.find((p) => p.key === 'provider')?.value,
      ).toBe('DeepSeek');
    });

    it('recognizes search engine switch intents', () => {
      const intentBing = parseNaturalLanguageConfigIntent('搜索换成必应 bing');
      expect(intentBing?.category).toBe('search_engine');
      expect(
        intentBing?.params.find((p) => p.key === 'search_engine')?.value,
      ).toBe('bing');

      const intentGoogle = parseNaturalLanguageConfigIntent('联网搜索切到谷歌');
      expect(
        intentGoogle?.params.find((p) => p.key === 'search_engine')?.value,
      ).toBe('google');
    });

    it('recognizes channel binding intents', () => {
      const intentFeishu = parseNaturalLanguageConfigIntent(
        '接入并绑定飞书群机器人',
      );
      expect(intentFeishu?.category).toBe('channel_binding');
      expect(
        intentFeishu?.params.find((p) => p.key === 'channel_type')?.value,
      ).toBe('feishu');

      const intentDingtalk = parseNaturalLanguageConfigIntent(
        '连上钉钉 dingtalk 机器人',
      );
      expect(
        intentDingtalk?.params.find((p) => p.key === 'channel_type')?.value,
      ).toBe('dingtalk');
    });

    it('returns null for unrelated conversational utterances', () => {
      expect(
        parseNaturalLanguageConfigIntent('今天天气真好，帮我写一首诗'),
      ).toBeNull();
    });
  });

  describe('validateConfigParams', () => {
    it('returns invalid if a secret parameter is empty', () => {
      const params: ConfigParamItem[] = [
        {
          key: 'api_key',
          label: 'API 授权凭据',
          type: 'password',
          value: '   ',
          isSecret: true,
        },
      ];
      const result = validateConfigParams(params);
      expect(result.valid).toBe(false);
      expect(result.errorMessage).toContain('请先填写「API 授权凭据」');
    });

    it('returns valid when all secret parameters are filled', () => {
      const params: ConfigParamItem[] = [
        {
          key: 'api_key',
          label: 'API 授权凭据',
          type: 'password',
          value: 'sk-12345678',
          isSecret: true,
        },
      ];
      const result = validateConfigParams(params);
      expect(result.valid).toBe(true);
      expect(result.errorMessage).toBeUndefined();
    });
  });
});
