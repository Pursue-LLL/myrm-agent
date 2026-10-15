import { create } from 'zustand';
import {
  PlaybookCategory,
  PlaybookScenario,
} from './nonCodingPlaybookTypes';

interface NonCodingPlaybookState {
  scenarios: PlaybookScenario[];
  selectedCategory: PlaybookCategory | 'all';
  searchKeyword: string;
  activeScenarioModal: PlaybookScenario | null;
  isComparisonModalOpen: boolean;
  formValues: Record<string, string>;

  setSelectedCategory: (cat: PlaybookCategory | 'all') => void;
  setSearchKeyword: (keyword: string) => void;
  openScenarioModal: (scenario: PlaybookScenario) => void;
  closeScenarioModal: () => void;
  updateFormField: (fieldId: string, value: string) => void;
  toggleComparisonModal: (open?: boolean) => void;
  reset: () => void;
}

export const INITIAL_PRESET_SCENARIOS: PlaybookScenario[] = [
  {
    id: 'sc-invoice-01',
    title: '智能发票报销整理与合规查重',
    category: 'finance',
    description:
      '批量扫描指定发票图片/PDF，自动 OCR 提取抬头、税号、金额，生成标准化报销 Excel 并高亮潜在重复报销项。',
    inputPlaceholder: '如：./my_invoices/ 目录下的 15 份电子发票',
    toolsUsed: ['ocr_scanner', 'excel_generator', 'file_system'],
    expectedOutput: '含明细、分类统计与查重标注的《2026年出差报销明细表.xlsx》',
    pipelineFlow: [
      '读取本地发票文件',
      '并行多线程 OCR 提取关键元数据',
      '比对公司财务报销规范',
      '生成带公式的 Excel 表格并写入本地',
    ],
    parameters: [
      {
        id: 'invoice_path',
        label: '发票所在文件夹路径',
        type: 'text',
        placeholder: '例如: ./documents/invoices/2026Q3',
        defaultValue: './invoices',
        required: true,
      },
      {
        id: 'company_title',
        label: '标准报销开票抬头',
        type: 'text',
        placeholder: '输入公司全称',
        defaultValue: '开放智能科技有限公司',
        required: true,
      },
      {
        id: 'expense_category',
        label: '报销业务类型',
        type: 'select',
        options: ['差旅交通住宿', '团队日常团建', '办公耗材采购', '客户业务招待'],
        defaultValue: '差旅交通住宿',
      },
    ],
    defaultPromptTemplate:
      '请帮我整理 {{invoice_path}} 目录下的所有发票。报销抬头必须为“{{company_title}}”，报销类别归为“{{expense_category}}”。请提取每张发票的日期、金额、发票代码与明细项目，查重后汇总导出为规范的 Excel 报销明细表。',
    starsCount: 382,
  },
  {
    id: 'sc-meeting-02',
    title: '复杂跨部门会议纪要转责任待办',
    category: 'admin',
    description:
      '把口语化散碎的会议录音速记文本，自动提炼为高层决策结论、核心分歧点，并自动拆解出精准到人、时间截点的 Action Items 矩阵。',
    inputPlaceholder: '粘贴 30 分钟产品规划会议的文字速记',
    toolsUsed: ['nlp_summarizer', 'markdown_exporter', 'todo_kanban'],
    expectedOutput: '高阶决策摘要 Markdown + 结构化负责人待办任务清单',
    pipelineFlow: [
      '消歧口语化废话与冗余语气词',
      '提取会议三大核心决议',
      '梳理跨部门待办与交付里程碑',
      '生成格式化《会议纪要与跟进表》',
    ],
    parameters: [
      {
        id: 'meeting_topic',
        label: '会议主题与部门',
        type: 'text',
        placeholder: '例如: Q4 战略落地跨部门同步会',
        defaultValue: '2026 年度重点项目冲刺会',
        required: true,
      },
      {
        id: 'output_format',
        label: '待办清单格式',
        type: 'select',
        options: ['标准 Markdown 表格', '看板待办卡片', '纯文本高亮列表'],
        defaultValue: '标准 Markdown 表格',
      },
    ],
    defaultPromptTemplate:
      '请分析本次《{{meeting_topic}}》的会议记录。去除口语化冗余内容，先总结 300 字以内的决策共识；再以 {{output_format}} 输出待办事项矩阵，列出事项名称、责任人、截止时间与验收标准。',
    starsCount: 295,
  },
  {
    id: 'sc-research-03',
    title: '50页行业长研报跨文件精炼对比',
    category: 'research',
    description:
      '对比两份长达数十页的券商行业研报，自动交叉验证行业增速预测、商业模式壁垒与关键财务指标差异，提炼决策内参。',
    inputPlaceholder: '输入两篇研报的 PDF 文件名或链接',
    toolsUsed: ['pdf_extractor', 'chart_analyzer', 'vector_search'],
    expectedOutput: '2000字深度决策内参 + 核心指标差异比对表格',
    pipelineFlow: [
      '解析研报目录与核心章节',
      '提取核心假设与量化增长模型',
      '双源交叉印证与矛盾观点对齐',
      '输出精炼高管决策内参简报',
    ],
    parameters: [
      {
        id: 'industry_focus',
        label: '聚焦行业/赛道',
        type: 'text',
        placeholder: '例如: 具身智能与大模型软硬一体',
        defaultValue: '生成式 AI 与前端交互变革',
        required: true,
      },
      {
        id: 'report_sources',
        label: '研报文件清单',
        type: 'text',
        placeholder: '例如: Report_A.pdf, Report_B.pdf',
        defaultValue: '2026_AI_UX_Trend.pdf, Gartner_Agent_Market.pdf',
      },
    ],
    defaultPromptTemplate:
      '请深入比对 {{report_sources}} 中关于 {{industry_focus}} 赛道的观点。重点对比双方对未来 3 年市场规模预期的差异及底层逻辑支撑，生成高管层级可直接审阅的精炼对比研报。',
    starsCount: 410,
  },
  {
    id: 'sc-legal-04',
    title: '商业服务合同条款合规风险排查',
    category: 'legal',
    description:
      '逐条款审查商业采购/SaaS 服务合同，自动标记赔偿上限缺失、知识产权模糊、单方解除权陷阱与不可抗力漏洞。',
    inputPlaceholder: '上传或粘贴商业采购合同初稿',
    toolsUsed: ['document_diff', 'legal_linter', 'annotator'],
    expectedOutput: '带修改建议批注的合规红线审查清单',
    pipelineFlow: [
      '按法务审查基线扫描各合同条款',
      '标红高危风险陷阱（如无上限赔付）',
      '给出符合我方利益的标准修改建议句式',
      '生成法务初审交涉备忘录',
    ],
    parameters: [
      {
        id: 'contract_type',
        label: '合同性质',
        type: 'select',
        options: ['甲方向乙方采购服务', '乙方向甲方交付系统', '战略合作保密框架', '劳务雇佣协议'],
        defaultValue: '甲方向乙方采购服务',
      },
      {
        id: 'strict_level',
        label: '合规审查严格度',
        type: 'select',
        options: ['严格审查（防守型）', '平衡撮合（促成交型）', '宽松浏览（通用型）'],
        defaultValue: '严格审查（防守型）',
      },
    ],
    defaultPromptTemplate:
      '我方作为{{contract_type}}的关系方，请以“{{strict_level}}”标准全面审查附带的合同条款。重点核查违约责任赔偿上限、知识产权权属归属与争议解决管辖地，列出不平等条款并提供专业修改文案。',
    starsCount: 312,
  },
  {
    id: 'sc-content-05',
    title: '全渠道爆款内容创作与分发排期',
    category: 'content',
    description:
      '给定一个核心产品概念，自动定制微信公众号长图文、小红书高赞图文笔记、推特/微博短文案及一周发布排期表。',
    inputPlaceholder: '例如：我们的开源全双工 AI 伙伴产品上线了',
    toolsUsed: ['style_transformer', 'calendar_scheduler', 'copywriting'],
    expectedOutput: '3 种差异化风格文案 + 7 天全平台发布时间日程表',
    pipelineFlow: [
      '解析核心传播卖点与目标受众画像',
      '按小红书/公众号/即刻等不同平台调性生成针对性文案',
      '搭配视觉配图构图指引',
      '规划最佳流量曝光发布时间轴',
    ],
    parameters: [
      {
        id: 'core_concept',
        label: '核心推广主题',
        type: 'text',
        placeholder: '例如: 全双工零阻塞 AI 桌面客户端正式开源',
        defaultValue: '极速 200ms 推测性握手 AI 助手体验',
        required: true,
      },
      {
        id: 'target_audience',
        label: '目标用户群体',
        type: 'text',
        placeholder: '例如: 程序员/产品经理/大学生',
        defaultValue: '追求极致效率的高阶极客与全栈工程师',
      },
    ],
    defaultPromptTemplate:
      '请围绕“{{core_concept}}”，面向“{{target_audience}}”创作一套全媒体传播内容组合。包含 1 篇小红书爆款文案（含标题、正文、标签）、1 条极客推文和 1 张 7 天发布节奏甘特图。',
    starsCount: 260,
  },
  {
    id: 'sc-general-06',
    title: '多项目跨组协同周报汇总统揽',
    category: 'general',
    description:
      '收集 5 个研发与运营小组的碎言碎语周报条目，自动消除重复，提炼关键里程碑攻克、延期风险预警与下周资源协调需求。',
    inputPlaceholder: '输入来自各个团队或飞书文档的本周工作零碎记录',
    toolsUsed: ['text_deduplicator', 'risk_predictor', 'report_generator'],
    expectedOutput: '总监/高管级跨项目综合周报汇报 Deck',
    pipelineFlow: [
      '汇总各小组周报条目并归类至项目主线',
      '自动识别逾期风险并亮黄红灯',
      '按“进展-风险-规划”三段式整合结构化总览',
      '导出专业格式化 Markdown 报告',
    ],
    parameters: [
      {
        id: 'report_week',
        label: '汇报所属周期',
        type: 'text',
        placeholder: '例如: 2026年第42周 (10.12 - 10.16)',
        defaultValue: '2026年第42周',
        required: true,
      },
    ],
    defaultPromptTemplate:
      '请将以下各组周报整合为《{{report_week}} 研发与交付综合统揽周报》。合并同类项，重点突出业务价值产出，明确标注需要跨部门协助的阻塞风险点，语言专业精炼。',
    starsCount: 188,
  },
];

export const useNonCodingPlaybookStore = create<NonCodingPlaybookState>(
  (set) => ({
    scenarios: INITIAL_PRESET_SCENARIOS,
    selectedCategory: 'all',
    searchKeyword: '',
    activeScenarioModal: null,
    isComparisonModalOpen: false,
    formValues: {},

    setSelectedCategory: (cat: PlaybookCategory | 'all'): void => {
      set({ selectedCategory: cat });
    },

    setSearchKeyword: (keyword: string): void => {
      set({ searchKeyword: keyword });
    },

    openScenarioModal: (scenario: PlaybookScenario): void => {
      // 预填充参数默认值
      const initialValues: Record<string, string> = {};
      for (const p of scenario.parameters) {
        if (p.defaultValue) {
          initialValues[p.id] = p.defaultValue;
        }
      }

      set({
        activeScenarioModal: scenario,
        formValues: initialValues,
      });
    },

    closeScenarioModal: (): void => {
      set({
        activeScenarioModal: null,
        formValues: {},
      });
    },

    updateFormField: (fieldId: string, value: string): void => {
      set((state) => ({
        formValues: {
          ...state.formValues,
          [fieldId]: value,
        },
      }));
    },

    toggleComparisonModal: (open?: boolean): void => {
      set((state) => ({
        isComparisonModalOpen:
          open !== undefined ? open : !state.isComparisonModalOpen,
      }));
    },

    reset: (): void => {
      set({
        scenarios: INITIAL_PRESET_SCENARIOS,
        selectedCategory: 'all',
        searchKeyword: '',
        activeScenarioModal: null,
        isComparisonModalOpen: false,
        formValues: {},
      });
    },
  }),
);
