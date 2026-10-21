import { describe, it, expect } from 'vitest';
import {
  classifySideChatIntent,
  generateInstantCollaboratorReply,
  createSteeringItemFromMessage,
  formatSteeringQueueForMainAgent,
} from '../sideChatEngine';
import { MainTaskProgressInfo, SideChatMessage, SteeringBufferItem } from '../sideChatTypes';

describe('sideChatEngine', () => {
  const mockTask: MainTaskProgressInfo = {
    taskId: 'task-1',
    taskName: '自动化组件重构',
    status: 'running',
    currentStep: 3,
    totalSteps: 6,
    currentStepDescription: '运行 Vitest 自动化测试套件',
  };

  it('准确分类支线对话意图', () => {
    expect(classifySideChatIntent('现在进行到哪一步了？')).toBe('status_inquiry');
    expect(classifySideChatIntent('查看当前任务进度与状态')).toBe('status_inquiry');

    expect(classifySideChatIntent('顺便加个导出 Excel 按钮')).toBe('incremental_feature');
    expect(classifySideChatIntent('还需要支持一键复制到剪贴板')).toBe('incremental_feature');

    expect(classifySideChatIntent('把超时阈值改成 5000ms')).toBe('parameter_override');
    expect(classifySideChatIntent('将系数配置修改为 1.5')).toBe('parameter_override');

    expect(classifySideChatIntent('等下记得把日志发给小王')).toBe('general_note');
  });

  it('协作者 Agent 毫秒级生成状态问答回复且不干扰主任务', () => {
    const statusReply = generateInstantCollaboratorReply('status_inquiry', '现在进度如何', mockTask);
    expect(statusReply).toContain('第 3/6 步');
    expect(statusReply).toContain('运行 Vitest 自动化测试套件');
    expect(statusReply).toContain('无需打断主线');

    const featureReply = generateInstantCollaboratorReply('incremental_feature', '增加导出功能', mockTask);
    expect(featureReply).toContain('非阻塞缓冲队列');
    expect(featureReply).toContain('增加导出功能');
  });

  it('正确将消息转换为排队条目并计算优先级', () => {
    const featureMsg: SideChatMessage = {
      id: 'msg-1',
      role: 'user',
      content: '加个导出功能',
      timestamp: Date.now(),
      intentType: 'incremental_feature',
    };
    const item = createSteeringItemFromMessage(featureMsg);

    expect(item.sourceMessageId).toBe('msg-1');
    expect(item.intentType).toBe('incremental_feature');
    expect(item.priority).toBe(8);
    expect(item.status).toBe('pending');

    const paramMsg: SideChatMessage = {
      id: 'msg-2',
      role: 'user',
      content: '改成 1.5',
      timestamp: Date.now(),
      intentType: 'parameter_override',
    };
    const paramItem = createSteeringItemFromMessage(paramMsg);
    expect(paramItem.priority).toBe(10);
  });

  it('将待吸收微调队列格式化为注入主 Agent 的系统提示词', () => {
    const items: SteeringBufferItem[] = [
      {
        id: 'st-1',
        sourceMessageId: 'm-1',
        intentType: 'incremental_feature',
        content: '增加导出 Excel 按钮',
        priority: 8,
        status: 'pending',
        createdAt: Date.now(),
      },
      {
        id: 'st-2',
        sourceMessageId: 'm-2',
        intentType: 'parameter_override',
        content: '系数改为 1.2',
        priority: 10,
        status: 'pending',
        createdAt: Date.now(),
      },
    ];

    const prompt = formatSteeringQueueForMainAgent(items);
    expect(prompt).toContain('【非阻塞支线补充调优指令 (Steering Injection)】');
    expect(prompt).toContain('[增量需求] 增加导出 Excel 按钮');
    expect(prompt).toContain('[参数覆写] 系数改为 1.2');
  });
});
