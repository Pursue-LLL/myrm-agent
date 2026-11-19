/**
 * [INPUT] 无（纯函数模块，入参为单条文案值 string / string[]）
 * [OUTPUT] NON_LATIN_RE / placeholderSet / isBilingualDirty / containsResidue / isEnglishSentenceResidue
 * [POS] verify-i18n 的纯文本判据（无 IO、无全局状态）：占位符集合、非拉丁文字、双语对照脏值、句子级纯英文残留。
 */

export function placeholderSet(value) {
  const matches = String(value).match(/\{([a-zA-Z_][\w.-]*)(?:,|})/g) || [];
  return matches
    .map((match) => match.replace(/^\{/, '').replace(/[,}]$/, ''))
    .sort()
    .join('|');
}

/**
 * 非拉丁文字区间（汉字 \u4e00-\u9fff、日文假名 \u3040-\u30ff、韩文谚文 \uac00-\ud7af、
 * 全角标点 \u3000-\u303f / \uff00-\uffef），用于 en 纯净性与双语对照检测。
 * 覆盖汉字之外的假名/谚文，杜绝其混入 en 或形成双语脏值而漏检。
 */
export const NON_LATIN_RE = /[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]/;

/**
 * 双语对照脏值：同一语义被写成"本地语 / English"（如 "是 / Yes"、"上下文健康 / Context Health"）。
 * 判定：恰好两段，一段纯 ASCII（英文），另一段含非拉丁文字（本地语），且不含 ICU 占位符对照。
 * 代码只排除占位符对照（{shown} / {total}）与超长值；合法的术语对照（如 MCP / 技能设置）
 * 须经 i18n-shell-allowlist.json 的 allowedMixedValues / allowedMixedKeys 显式豁免。
 */
export function isBilingualDirty(value) {
  if (typeof value !== 'string' || value.length > 160) {
    return false;
  }
  if (!NON_LATIN_RE.test(value) || !/[a-zA-Z]/.test(value)) {
    return false;
  }
  if (!value.includes(' / ') || /\{/.test(value)) {
    return false;
  }
  const parts = value.split(' / ');
  if (parts.length !== 2) {
    return false;
  }
  const [a, b] = parts.map((s) => s.trim());
  if (!a || !b) {
    return false;
  }
  const asciiOnly = (s) => s.length > 0 && [...s].every((c) => c.charCodeAt(0) <= 0x7f);
  const nonLatinOnly = (s) => !/[a-zA-Z]/.test(s) && NON_LATIN_RE.test(s);
  return (asciiOnly(a) && nonLatinOnly(b)) || (nonLatinOnly(a) && asciiOnly(b));
}

/**
 * 值是否含指定残留字形：字符串直接检测，数组逐元素检测字符串成员。
 * 与 9d checkArray 对齐，覆盖数组叶子（i18n 选项列表）的纯净性，
 * 避免 9f 对数组 leaf 漏检。
 */
export function containsResidue(value, residueRe) {
  if (typeof value === 'string') {
    return residueRe.test(value);
  }
  if (Array.isArray(value)) {
    return value.some((item) => typeof item === 'string' && residueRe.test(item));
  }
  return false;
}

/**
 * 9k 句子级纯英文残留判定（zh）：
 * 非拉丁系语言的整条文案若仍是英文句子（含 ≥2 个纯字母英文单词且带句尾标点
 * 或英文功能词），即未本地化残留。
 *
 * 判定为「句子级」而非「任意英文」：
 * - ≥2 个纯字母单词：排除单技术词（Agent/Token/Cookie）。
 * - 句尾标点 `! . ?` 或功能词命中：排除字段名/品牌名（App ID/Bot Token/
 *   Alibaba Cloud/Client Secret），这些是行业惯例保留英文的凭据名，翻译反而
 *   降低可识别性（用户从文档/API 得知的是英文术语）。
 */
const PURE_EN_SENTENCE_WORDS_RE = /[A-Za-z]{2,}/g;
const PURE_EN_SENTENCE_TAIL_RE = /[!?.]$/;
// prettier-ignore
const PURE_EN_FUNCTION_WORDS = new Set([
  // UI 动作/状态词
  'login', 'logged', 'sign', 'successful', 'success', 'failed', 'fail', 'error', 'please',
  'click', 'expires', 'expired', 'waiting', 'wait', 'authorize', 'authorization', 'authorized',
  'connecting', 'connected', 'connect', 'generating', 'generate', 'select', 'scan', 'start',
  'prepare', 'preparing', 'validate', 'validating', 'cancel', 'cancelled', 'canceled', 'timeout',
  'retry', 'unknown', 'initializing', 'loading', 'saving', 'save', 'open', 'close', 'done',
  'completed', 'complete', 'processing', 'process', 'running', 'run', 'resumed', 'resume',
  'enabled', 'disabled', 'available', 'unavailable', 'missing', 'required', 'optional',
  'create', 'created', 'update', 'updated', 'remove', 'removed', 'add', 'added', 'search',
  'refresh', 'send', 'sent', 'receive', 'received', 'import', 'export', 'download', 'upload',
  'install', 'uninstall', 'enable', 'disable', 'verify', 'verification', 'check', 'testing',
  'test', 'connection', 'disconnect', 'disconnected', 'reconnect', 'pending', 'approved',
  'rejected', 'deleted', 'archived', 'restored', 'upgrade', 'subscribe', 'purchase',
  'confirm', 'delete', 'back', 'next', 'reset', 'restore', 'backup', 'migrate', 'migration',
  'share', 'shared', 'sync', 'paused', 'pause', 'blocked', 'unblocked', 'approve',
  // 英文虚词（句子结构标记）
  'the', 'a', 'an', 'of', 'at', 'for', 'with', 'and', 'or', 'to', 'from', 'by', 'in', 'on',
  'your', 'you', 'is', 'are', 'was', 'were', 'has', 'have', 'will', 'would', 'can', 'could',
  'should', 'must', 'not', 'no', 'yes', 'this', 'that', 'these', 'those', 'there', 'here',
  'more', 'less', 'all', 'any', 'some', 'none', 'only', 'just', 'also', 'then', 'than',
  'into', 'onto', 'over', 'under', 'about', 'after', 'before', 'during', 'between',
]);

export function isEnglishSentenceResidue(value) {
  const words = value.toLowerCase().match(PURE_EN_SENTENCE_WORDS_RE) ?? [];
  if (words.length < 2) {
    return false;
  }
  if (PURE_EN_SENTENCE_TAIL_RE.test(value.trim())) {
    return true;
  }
  return words.some((word) => PURE_EN_FUNCTION_WORDS.has(word));
}
