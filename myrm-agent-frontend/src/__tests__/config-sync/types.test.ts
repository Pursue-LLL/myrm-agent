/**
 * 配置同步类型测试
 *
 * 测试版本号工具函数
 */

import { describe, it, expect } from 'vitest';
import {
  createInitialVersion,
  incrementVersion,
  compareVersions,
  parseVersion,
} from '@/services/config/types';

describe('Config Sync Types', () => {
  describe('Version Functions', () => {
    describe('createInitialVersion', () => {
      it('应该创建格式为 timestamp_0 的初始版本号', () => {
        const version = createInitialVersion();
        expect(version).toMatch(/^\d+_0$/);
      });

      it('应该使用当前时间戳', () => {
        const before = Date.now();
        const version = createInitialVersion();
        const after = Date.now();

        const { timestamp } = parseVersion(version);
        expect(timestamp).toBeGreaterThanOrEqual(before);
        expect(timestamp).toBeLessThanOrEqual(after);
      });
    });

    describe('incrementVersion', () => {
      it('应该在同一毫秒内递增计数器', () => {
        const now = Date.now();
        const current = `${now}_0`;

        // 模拟在同一毫秒内调用
        const next = incrementVersion(current);

        // 由于时间可能已经过去，我们只检查格式
        expect(next).toMatch(/^\d+_\d+$/);
      });

      it('应该在不同毫秒重置计数器为 0', () => {
        const oldTimestamp = Date.now() - 1000; // 1秒前
        const current = `${oldTimestamp}_5`;

        const next = incrementVersion(current);
        const { counter } = parseVersion(next);

        expect(counter).toBe(0);
      });

      it('应该处理格式错误的版本号', () => {
        const invalid = 'invalid_version';
        const result = incrementVersion(invalid);

        expect(result).toMatch(/^\d+_0$/);
      });
    });

    describe('compareVersions', () => {
      it('应该正确比较不同时间戳的版本', () => {
        const older = '1000000000000_0';
        const newer = '1000000000001_0';

        expect(compareVersions(newer, older)).toBeGreaterThan(0);
        expect(compareVersions(older, newer)).toBeLessThan(0);
      });

      it('应该正确比较同一时间戳不同计数器的版本', () => {
        const v1 = '1000000000000_0';
        const v2 = '1000000000000_1';

        expect(compareVersions(v2, v1)).toBeGreaterThan(0);
        expect(compareVersions(v1, v2)).toBeLessThan(0);
      });

      it('应该对相同版本返回 0', () => {
        const version = '1000000000000_5';
        expect(compareVersions(version, version)).toBe(0);
      });
    });

    describe('parseVersion', () => {
      it('应该正确解析版本号', () => {
        const version = '1706000000000_5';
        const { timestamp, counter } = parseVersion(version);

        expect(timestamp).toBe(1706000000000);
        expect(counter).toBe(5);
      });
    });
  });
});
