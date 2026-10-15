'use client';

import { DesignElementKey, FiveElementSpec, DesignDirectionVariant } from './designIntentTypes';

export const QUICK_OPTIONS_MAP: Record<DesignElementKey, string[]> = {
  what: ['宣传海报', '移动端APP界面', '电商Banner', '活动邀请函', '品牌宣传单'],
  audience: ['年轻都市白领', '高校青年学生', '商务企业高管', '大众全年龄客群', '科技极客开发者'],
  style: ['温暖复古质感', '极简科技留白', '新锐赛博朋克', '活力明亮轻快', '暗黑高端轻奢'],
  content: ['第二杯半价特惠', '品牌十周年庆典', '立即预约体验', '限量首发抢购', '重磅新品发布'],
  format: ['A3竖版印刷 (300dpi)', '手机端全屏 (9:16)', '微信公众号横图 (2.35:1)', '桌面宽屏 (16:9)', '社交方图 (1:1)'],
};

const ELEMENT_MATCHERS: Record<DesignElementKey, RegExp> = {
  what: /(海报|APP|界面|应用|页面|banner|宣传单|单页|画报|封面|插画|logo|卡片|工作台)/i,
  audience: /(白领|年轻人|青年|学生|高管|大众|儿童|亲子|极客|开发者|商务|女性|老年)/i,
  style: /(复古|极简|科技|赛博|朋克|商务|扁平|插画|明亮|暗黑|轻奢|手绘|二次元|新拟态|毛玻璃)/i,
  content: /(标题|文案|折扣|半价|周年|庆典|活动|时间|地点|特惠|优惠|立即|免费|抢购)/i,
  format: /(a3|a4|竖版|横版|9:16|16:9|2.35:1|1:1|全屏|手机端|印刷|分辨率|长图)/i,
};

/**
 * 意图五要素动态语义检测器
 */
export function analyzeFiveElements(input: string): FiveElementSpec {
  const trimmed = input.trim();
  const keys: DesignElementKey[] = ['what', 'audience', 'style', 'content', 'format'];
  const labels: Record<DesignElementKey, string> = {
    what: '做什么',
    audience: '给谁看',
    style: '什么风格',
    content: '内容清单',
    format: '尺寸用途',
  };

  const specParts = {} as Record<DesignElementKey, FiveElementSpec[DesignElementKey]>;
  let detectedCount = 0;

  for (const key of keys) {
    const matcher = ELEMENT_MATCHERS[key];
    const match = trimmed.match(matcher);
    const isDetected = Boolean(match);

    if (isDetected) {
      detectedCount += 1;
    }

    specParts[key] = {
      key,
      label: labels[key],
      value: match ? match[0] : null,
      isDetected,
      quickOptions: QUICK_OPTIONS_MAP[key],
    };
  }

  const completenessScore = Math.round((detectedCount / keys.length) * 100);

  return {
    ...specParts,
    completenessScore,
  };
}

/**
 * 将五要素补齐组装为高精准度商业设计 Prompt
 */
export function assembleRefinedPrompt(spec: FiveElementSpec, rawPrompt: string): string {
  const what = spec.what.value || '设计海报';
  const audience = spec.audience.value ? `目标受众为${spec.audience.value}` : '面向大众用户';
  const style = spec.style.value ? `采用${spec.style.value}视觉风格` : '具备专业设计质感';
  const content = spec.content.value ? `核心文案包含「${spec.content.value}」` : '';
  const format = spec.format.value ? `规格尺寸为${spec.format.value}` : '标准通用尺寸';

  const clauses = [
    `请设计制作一份专业的【${what}】`,
    audience,
    style,
    content,
    format,
  ].filter(Boolean);

  let result = clauses.join('，') + '。';
  if (rawPrompt && !clauses.some((c) => rawPrompt.includes(c))) {
    result += ` 补充要求：${rawPrompt}`;
  }

  return result;
}

/**
 * 初稿阶段：根据五要素发散生成 3 组差异化初稿方案
 */
export function generateInitial3Directions(spec: FiveElementSpec): DesignDirectionVariant[] {
  const mainSubject = spec.what.value || '宣传设计物';
  const mainStyle = spec.style.value || '现代科技';

  return [
    {
      id: 'direction-a-minimal',
      title: '方向 A · 极简留白典范',
      subtitle: '大面积优雅负空间，强调文字排版节奏与精细网格',
      aestheticCategory: '极简排版型 (Minimal Zen)',
      primaryColor: '#0ea5e9',
      accentColor: '#38bdf8',
      backgroundColor: '#020617',
      layoutStructure: 'minimal',
      summary: `针对${mainSubject}，运用大面积干净呼吸留白，剔除杂乱装饰，突出标题信息层级与纯粹的视觉穿透力。`,
      previewLayers: [
        { id: 'p1', name: '大标题文字', type: 'text', text: `${mainSubject} · 纯粹精萃`, color: '#f8fafc', height: 28 },
        { id: 'p2', name: '极简细分割线', type: 'container', bg: '#1e293b', height: 2 },
        { id: 'p3', name: '主行动按钮', type: 'button', text: '即刻探索 ➔', bg: '#0ea5e9', color: '#ffffff', borderRadius: 4, height: 38 },
      ],
    },
    {
      id: 'direction-b-bold',
      title: '方向 B · 视觉张力冲击',
      subtitle: '高对比饱满色块与动感构图，强烈抓取第一视觉焦点',
      aestheticCategory: '视觉冲击型 (Bold Impact)',
      primaryColor: '#f43f5e',
      accentColor: '#fb7185',
      backgroundColor: '#18181b',
      layoutStructure: 'bold-visual',
      summary: `融入${mainStyle}精髓，通过高饱和色块对撞与大号黑体标题，形成震撼的视觉冲击力，极适合社交营销抓人眼球。`,
      previewLayers: [
        { id: 'p4', name: '视觉冲击色块', type: 'container', bg: '#f43f5e', borderRadius: 16, height: 90 },
        { id: 'p5', name: '重磅主标题', type: 'text', text: `HOT · 震撼首发`, color: '#ffffff', height: 32 },
        { id: 'p6', name: '荧光行动胶囊', type: 'button', text: '立享特惠折扣', bg: '#fbbf24', color: '#000000', borderRadius: 24, height: 42 },
      ],
    },
    {
      id: 'direction-c-cards',
      title: '方向 C · 结构卡片阵列',
      subtitle: '模块化高质感卡片布局，严谨承载多维度丰富信息',
      aestheticCategory: '结构卡片型 (Structured Cards)',
      primaryColor: '#6366f1',
      accentColor: '#818cf8',
      backgroundColor: '#0f172a',
      layoutStructure: 'structured-card',
      summary: `采用毛玻璃分块卡片承载信息，图文层次分明，规整利落，特别适合功能复杂的商业级界面与全案交付。`,
      previewLayers: [
        { id: 'p7', name: '毛玻璃信息卡片1', type: 'container', bg: 'rgba(30, 41, 59, 0.8)', borderRadius: 12, height: 48 },
        { id: 'p8', name: '毛玻璃信息卡片2', type: 'container', bg: 'rgba(30, 41, 59, 0.8)', borderRadius: 12, height: 48 },
        { id: 'p9', name: '规范化提交按钮', type: 'button', text: '查看完整方案', bg: '#6366f1', color: '#ffffff', borderRadius: 10, height: 40 },
      ],
    },
  ];
}
