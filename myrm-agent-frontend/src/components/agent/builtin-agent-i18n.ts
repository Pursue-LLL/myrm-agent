/**
 * [INPUT]
 * (none - pure data module)
 *
 * [OUTPUT]
 * BUILTIN_AGENT_I18N: 内置智能体的多语言名称与描述映射
 * getBuiltinAgentName: 根据 agent ID 和 locale 获取本地化名称
 * getBuiltinAgentDescription: 根据 agent ID 和 locale 获取本地化描述
 *
 * [POS]
 * 内置智能体国际化数据层。提供 builtin agent 的多语言翻译（en/zh/ja/ko/de），
 * 使 UI 展示时可按用户 locale 显示本地化名称/描述。
 */

interface LocaleStrings {
  name: string;
  description: string;
}

interface AgentI18nEntry {
  en: LocaleStrings;
  zh: LocaleStrings;
  ja: LocaleStrings;
  ko: LocaleStrings;
  de: LocaleStrings;
}

const BUILTIN_AGENT_I18N: Record<string, AgentI18nEntry> = {
  'builtin-general': {
    en: {
      name: 'General Assistant',
      description: 'Versatile AI assistant for everyday tasks — writing, analysis, Q&A, brainstorming, and more.',
    },
    zh: { name: '通用助手', description: '多功能 AI 助手，适用于日常写作、分析、问答、头脑风暴等各类任务。' },
    ja: {
      name: '汎用アシスタント',
      description: '日常のライティング、分析、Q&A、ブレインストーミングなど多目的AIアシスタント。',
    },
    ko: {
      name: '범용 어시스턴트',
      description: '일상적인 글쓰기, 분석, Q&A, 브레인스토밍 등 다양한 작업을 위한 AI 어시스턴트.',
    },
    de: {
      name: 'Allzweck-Assistent',
      description:
        'Vielseitiger KI-Assistent für alltägliche Aufgaben — Schreiben, Analyse, Q&A, Brainstorming und mehr.',
    },
  },
  'builtin-writer': {
    en: {
      name: 'Content Creator',
      description: 'Expert in writing, editing, copywriting, and content strategy with a creative flair.',
    },
    zh: { name: '内容创作者', description: '擅长写作、编辑、文案创意与内容策略，兼具创意灵感。' },
    ja: {
      name: 'コンテンツクリエイター',
      description: 'ライティング、編集、コピーライティング、コンテンツ戦略のエキスパート。',
    },
    ko: { name: '콘텐츠 크리에이터', description: '글쓰기, 편집, 카피라이팅, 콘텐츠 전략에 능한 크리에이티브 전문가.' },
    de: {
      name: 'Content-Ersteller',
      description: 'Experte für Texterstellung, Redaktion, Werbetexte und Content-Strategie mit kreativem Flair.',
    },
  },
  'builtin-researcher': {
    en: {
      name: 'Research Analyst',
      description:
        'Deep research and analysis — structured reports, data-driven insights, and multi-angle investigation.',
    },
    zh: { name: '研究分析师', description: '深度研究与分析——结构化报告、数据驱动洞察、多角度调研。' },
    ja: {
      name: 'リサーチアナリスト',
      description: '深い調査と分析 — 構造化レポート、データドリブンな洞察、多角的調査。',
    },
    ko: {
      name: '리서치 애널리스트',
      description: '심층 리서치와 분석 — 구조화된 보고서, 데이터 기반 인사이트, 다각도 조사.',
    },
    de: {
      name: 'Research-Analyst',
      description:
        'Tiefgehende Recherche und Analyse — strukturierte Berichte, datengetriebene Erkenntnisse und Mehrwinkel-Untersuchung.',
    },
  },
  'builtin-developer': {
    en: {
      name: 'Code Developer',
      description: 'Focused coding assistant — write, debug, review, and optimize code with precision.',
    },
    zh: { name: '代码开发者', description: '专注的编程助手——精准编写、调试、审查和优化代码。' },
    ja: {
      name: 'コード開発者',
      description: '集中型コーディングアシスタント — 正確にコードを書き、デバッグ、レビュー、最適化。',
    },
    ko: { name: '코드 개발자', description: '집중형 코딩 어시스턴트 — 정밀하게 코드 작성, 디버그, 리뷰, 최적화.' },
    de: {
      name: 'Code-Entwickler',
      description: 'Fokussierter Coding-Assistent — präzises Schreiben, Debuggen, Überprüfen und Optimieren von Code.',
    },
  },
  'builtin-translator': {
    en: {
      name: 'Translator',
      description: 'Professional multilingual translation and localization — faithful, natural, culturally adapted.',
    },
    zh: { name: '翻译专家', description: '专业多语种翻译与本地化——忠实原意、表达自然、文化适配。' },
    ja: {
      name: '翻訳エキスパート',
      description: 'プロフェッショナルな多言語翻訳とローカライゼーション — 忠実で自然、文化に適応。',
    },
    ko: {
      name: '번역 전문가',
      description: '전문 다국어 번역과 로컬라이제이션 — 충실하고 자연스럽고 문화에 맞는 번역.',
    },
    de: {
      name: 'Übersetzer',
      description: 'Professionelle mehrsprachige Übersetzung und Lokalisierung — treu, natürlich, kulturell angepasst.',
    },
  },
  'builtin-social-media': {
    en: {
      name: 'Social Media Strategist',
      description:
        'Content creation for Xiaohongshu, Douyin, Bilibili, Twitter, Instagram — platform-native copy and strategy.',
    },
    zh: { name: '社媒策略师', description: '为小红书、抖音、B站、Twitter、Instagram 创作平台原生内容与策略。' },
    ja: {
      name: 'SNSストラテジスト',
      description: 'Xiaohongshu、Douyin、Bilibili、Twitter、Instagram向けプラットフォームネイティブコンテンツ制作。',
    },
    ko: {
      name: '소셜미디어 전략가',
      description: '샤오홍슈, 더우인, 비리비리, Twitter, Instagram용 플랫폼 네이티브 콘텐츠 제작과 전략.',
    },
    de: {
      name: 'Social-Media-Stratege',
      description:
        'Content-Erstellung für Xiaohongshu, Douyin, Bilibili, Twitter, Instagram — plattformgerechte Texte und Strategie.',
    },
  },
  'builtin-data-analyst': {
    en: {
      name: 'Data Analyst',
      description: 'Data analysis, visualization recommendations, SQL, and insight extraction from structured data.',
    },
    zh: { name: '数据分析师', description: '数据分析、可视化建议、SQL 编写与结构化数据洞察提取。' },
    ja: { name: 'データアナリスト', description: 'データ分析、可視化推奨、SQL、構造化データからのインサイト抽出。' },
    ko: { name: '데이터 분석가', description: '데이터 분석, 시각화 추천, SQL, 구조화된 데이터에서 인사이트 추출.' },
    de: {
      name: 'Datenanalyst',
      description: 'Datenanalyse, Visualisierungsempfehlungen, SQL und Erkenntnisgewinnung aus strukturierten Daten.',
    },
  },
  'builtin-product-manager': {
    en: {
      name: 'Product Manager',
      description: 'PRD writing, competitive analysis, requirement breakdown, user story mapping, and prioritization.',
    },
    zh: { name: '产品经理', description: 'PRD 撰写、竞品分析、需求拆解、用户故事梳理与优先级排序。' },
    ja: {
      name: 'プロダクトマネージャー',
      description: 'PRD作成、競合分析、要件分解、ユーザーストーリーマッピング、優先順位付け。',
    },
    ko: {
      name: '프로덕트 매니저',
      description: 'PRD 작성, 경쟁 분석, 요구사항 분해, 유저 스토리 매핑, 우선순위 결정.',
    },
    de: {
      name: 'Produktmanager',
      description:
        'PRD-Erstellung, Wettbewerbsanalyse, Anforderungsaufschlüsselung, User-Story-Mapping und Priorisierung.',
    },
  },
  'builtin-tutor': {
    en: {
      name: 'Tutor',
      description:
        'Patient teaching assistant — explain concepts, answer questions, create study plans, and guide learning.',
    },
    zh: { name: '学习导师', description: '耐心的教学助手——讲解概念、解答疑问、制定学习计划、引导学习。' },
    ja: {
      name: 'チューター',
      description: '辛抱強い教育アシスタント — 概念説明、質問対応、学習計画作成、学習ガイド。',
    },
    ko: { name: '튜터', description: '인내심 있는 학습 어시스턴트 — 개념 설명, 질문 응답, 학습 계획 수립, 학습 안내.' },
    de: {
      name: 'Tutor',
      description:
        'Geduldiger Lehrassistent — Konzepte erklären, Fragen beantworten, Lernpläne erstellen und Lernen begleiten.',
    },
  },
  'builtin-newsletter': {
    en: {
      name: 'Newsletter Editor',
      description: 'Research topics, write engaging newsletters, manage editorial calendars, and optimize open rates.',
    },
    zh: { name: 'Newsletter 编辑', description: '选题调研、撰写有吸引力的通讯内容、管理编辑日历、优化打开率。' },
    ja: {
      name: 'ニュースレター編集者',
      description: 'トピックリサーチ、魅力的なニュースレター作成、編集カレンダー管理、開封率最適化。',
    },
    ko: {
      name: '뉴스레터 에디터',
      description: '주제 리서치, 매력적인 뉴스레터 작성, 에디토리얼 캘린더 관리, 오픈율 최적화.',
    },
    de: {
      name: 'Newsletter-Redakteur',
      description:
        'Themenrecherche, ansprechende Newsletter verfassen, Redaktionskalender verwalten und Öffnungsraten optimieren.',
    },
  },
  'builtin-design': {
    en: {
      name: 'Design Advisor',
      description: 'UI/UX feedback, color theory, typography guidance, layout critique, and design system advice.',
    },
    zh: { name: '设计顾问', description: 'UI/UX 反馈、色彩理论、字体指导、布局评审与设计系统建议。' },
    ja: {
      name: 'デザインアドバイザー',
      description: 'UI/UXフィードバック、カラー理論、タイポグラフィガイダンス、レイアウト評価、デザインシステム助言。',
    },
    ko: {
      name: '디자인 어드바이저',
      description: 'UI/UX 피드백, 색상 이론, 타이포그래피 가이드, 레이아웃 평가, 디자인 시스템 조언.',
    },
    de: {
      name: 'Design-Berater',
      description: 'UI/UX-Feedback, Farbtheorie, Typografie-Anleitung, Layout-Kritik und Design-System-Beratung.',
    },
  },
  'builtin-seo': {
    en: {
      name: 'SEO Strategist',
      description: 'Keyword research, content optimization, technical SEO audits, and competitive SERP analysis.',
    },
    zh: { name: 'SEO 策略师', description: '关键词研究、内容优化、技术 SEO 审计与竞争 SERP 分析。' },
    ja: {
      name: 'SEOストラテジスト',
      description: 'キーワードリサーチ、コンテンツ最適化、テクニカルSEO監査、競合SERP分析。',
    },
    ko: { name: 'SEO 전략가', description: '키워드 리서치, 콘텐츠 최적화, 테크니컬 SEO 감사, 경쟁 SERP 분석.' },
    de: {
      name: 'SEO-Stratege',
      description: 'Keyword-Recherche, Content-Optimierung, technische SEO-Audits und Wettbewerbs-SERP-Analyse.',
    },
  },
  'builtin-scheduler': {
    en: {
      name: 'Schedule Planner',
      description:
        'Task decomposition, time blocking, priority management, deadline tracking, and productivity systems.',
    },
    zh: { name: '日程规划师', description: '任务拆解、时间块规划、优先级管理、截止日期跟踪与效率系统。' },
    ja: {
      name: 'スケジュールプランナー',
      description: 'タスク分解、タイムブロッキング、優先度管理、締切追跡、生産性システム。',
    },
    ko: { name: '일정 플래너', description: '태스크 분해, 타임 블로킹, 우선순위 관리, 마감일 추적, 생산성 시스템.' },
    de: {
      name: 'Zeitplaner',
      description:
        'Aufgabenzerlegung, Zeitblockierung, Prioritätsmanagement, Terminverfolgung und Produktivitätssysteme.',
    },
  },
  'builtin-meeting': {
    en: {
      name: 'Meeting Scribe',
      description: 'Extract key points, decisions, action items, and follow-ups from meeting notes or transcripts.',
    },
    zh: { name: '会议纪要员', description: '从会议记录中提取要点、决策、行动项与后续跟进事项。' },
    ja: {
      name: '会議スクライブ',
      description: '会議メモや議事録から要点、決定事項、アクションアイテム、フォローアップを抽出。',
    },
    ko: {
      name: '회의록 작성자',
      description: '회의 노트나 녹취록에서 핵심 포인트, 결정 사항, 액션 아이템, 후속 조치를 추출.',
    },
    de: {
      name: 'Meeting-Protokollant',
      description:
        'Kernpunkte, Entscheidungen, Aktionspunkte und Follow-ups aus Meeting-Notizen oder Transkripten extrahieren.',
    },
  },
  'builtin-career': {
    en: {
      name: 'Career Coach',
      description: 'Resume optimization, interview prep, career planning, networking strategy, and salary negotiation.',
    },
    zh: { name: '职业教练', description: '简历优化、面试准备、职业规划、人脉策略与薪资谈判。' },
    ja: {
      name: 'キャリアコーチ',
      description: '履歴書最適化、面接対策、キャリアプランニング、ネットワーキング戦略、給与交渉。',
    },
    ko: { name: '커리어 코치', description: '이력서 최적화, 면접 준비, 커리어 계획, 네트워킹 전략, 연봉 협상.' },
    de: {
      name: 'Karriere-Coach',
      description:
        'Lebenslauf-Optimierung, Interviewvorbereitung, Karriereplanung, Networking-Strategie und Gehaltsverhandlung.',
    },
  },
  'builtin-finance': {
    en: {
      name: 'Finance Advisor',
      description: 'Budget analysis, investment basics, expense tracking strategies, and personal financial planning.',
    },
    zh: { name: '理财顾问', description: '预算分析、投资基础、支出管理策略与个人财务规划。' },
    ja: {
      name: 'ファイナンスアドバイザー',
      description: '予算分析、投資基礎、支出管理戦略、パーソナルファイナンス計画。',
    },
    ko: { name: '재무 어드바이저', description: '예산 분석, 투자 기초, 지출 관리 전략, 개인 재무 계획.' },
    de: {
      name: 'Finanzberater',
      description:
        'Budgetanalyse, Investitionsgrundlagen, Ausgabenverfolgungsstrategien und persönliche Finanzplanung.',
    },
  },
  'builtin-travel': {
    en: {
      name: 'Travel Planner',
      description: 'Itinerary design, destination research, budget optimization, and local experience recommendations.',
    },
    zh: { name: '旅行规划师', description: '行程设计、目的地研究、预算优化与本地体验推荐。' },
    ja: {
      name: '旅行プランナー',
      description: '旅程設計、目的地リサーチ、予算最適化、ローカル体験レコメンデーション。',
    },
    ko: { name: '여행 플래너', description: '일정 설계, 목적지 리서치, 예산 최적화, 로컬 경험 추천.' },
    de: {
      name: 'Reiseplaner',
      description: 'Reiseplanung, Zielrecherche, Budgetoptimierung und lokale Erlebnisempfehlungen.',
    },
  },
  'builtin-email': {
    en: {
      name: 'Email Expert',
      description: 'Professional email drafting — cold outreach, follow-ups, negotiations, and business communication.',
    },
    zh: { name: '邮件专家', description: '专业邮件撰写——冷启动触达、跟进邮件、商务谈判与沟通。' },
    ja: {
      name: 'メールエキスパート',
      description:
        'プロフェッショナルなメール作成 — コールドアウトリーチ、フォローアップ、交渉、ビジネスコミュニケーション。',
    },
    ko: {
      name: '이메일 전문가',
      description: '전문 이메일 작성 — 콜드 아웃리치, 팔로업, 협상, 비즈니스 커뮤니케이션.',
    },
    de: {
      name: 'E-Mail-Experte',
      description:
        'Professionelles E-Mail-Verfassen — Kaltakquise, Follow-ups, Verhandlungen und Geschäftskommunikation.',
    },
  },
  'builtin-automation': {
    en: {
      name: 'Automation Builder',
      description: 'Workflow design, task automation strategies, integration planning, and efficiency optimization.',
    },
    zh: { name: '自动化构建师', description: '工作流设计、任务自动化策略、集成规划与效率优化。' },
    ja: {
      name: 'オートメーションビルダー',
      description: 'ワークフロー設計、タスク自動化戦略、インテグレーション計画、効率最適化。',
    },
    ko: { name: '자동화 빌더', description: '워크플로우 설계, 태스크 자동화 전략, 통합 계획, 효율성 최적화.' },
    de: {
      name: 'Automatisierungs-Architekt',
      description: 'Workflow-Design, Aufgabenautomatisierungsstrategien, Integrationsplanung und Effizienzoptimierung.',
    },
  },
};

type SupportedLocale = 'en' | 'zh' | 'ja' | 'ko' | 'de';

function resolveLocale(locale: string): SupportedLocale {
  if (locale.startsWith('zh')) return 'zh';
  if (locale.startsWith('ja')) return 'ja';
  if (locale.startsWith('ko')) return 'ko';
  if (locale.startsWith('de')) return 'de';
  return 'en';
}

export function getBuiltinAgentName(agentId: string, agentName: string, locale: string): string {
  const entry = BUILTIN_AGENT_I18N[agentId];
  if (!entry) return agentName;
  return entry[resolveLocale(locale)]?.name ?? agentName;
}

export function getBuiltinAgentDescription(agentId: string, agentDescription: string, locale: string): string {
  const entry = BUILTIN_AGENT_I18N[agentId];
  if (!entry) return agentDescription;
  return entry[resolveLocale(locale)]?.description ?? agentDescription;
}
