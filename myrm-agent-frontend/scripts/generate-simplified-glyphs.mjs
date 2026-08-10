#!/usr/bin/env node
/**
 * 从 zh.json（简体 SSOT）语料生成 zh-TW / ja 的简体独有字形集合。
 *
 * 输出：
 * - scripts/zh-simplified-glyphs.txt：简体→繁体独有字形，供 verify-i18n.mjs 9h（zh-TW 纯净门禁）
 * - scripts/ja-simplified-glyphs.txt：简体→日文新字体独有字形，供 verify-i18n.mjs 9j（ja 纯净门禁）
 *
 * 残留源头是 zh（简体）文案复制到 zh-TW / ja，覆盖 zh 语料中的全部简繁/简日
 * 异形字即对项目文案完备。各目标语言存在合法的同形字（如繁体「台/准/于」、
 * 日文「体/与/云」），通过 TARGETS.legal 豁免以防误伤。
 *
 * 用法：bun scripts/generate-simplified-glyphs.mjs（自动写入脚本同目录）
 *       bun scripts/generate-simplified-glyphs.mjs --check（仅校验集合是否最新，供 pretest/CI）
 * 依赖：opencc-js（devDependency，cn→tw / cn→jp 单字转换）
 * 注意：zh.json 新增简体字后应重跑本脚本刷新集合。
 */
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { Converter } from 'opencc-js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');

/**
 * 各目标语言配置：转换方言、合法豁免字、输出文件。
 * - zh-TW 豁免：台（平台/台灣）、准（批准）、于（姓氏/介词）、伙（伙伴）、
 *   占（占卜/佔領）、里（公里/阿里）、游（上游/游泳）、干（干涉/干預）——台湾标准合法两体字。
 * - ja 豁免：体（身体/体験）、与（与える）、云（雲/云々）、个（個の略）、
 *   台（台湾/台所）、准（批准）、于（於の通仮）、占（占める）、里（里山）、
 *   游（遊の通仮）、干（乾/干涉）、伙（伙伴の伙）、携（携帯）、进（進の略）、
 *   万（万）、发（発の略）、当（当）、回（回）——日文新字体与简体同形或日语合法用字。
 */
const TARGETS = [
  {
    name: 'zh-TW',
    output: 'zh-simplified-glyphs.txt',
    converter: Converter({ from: 'cn', to: 'tw' }),
    legal: new Set('台准于伙占里游干'),
  },
  {
    name: 'ja',
    output: 'ja-simplified-glyphs.txt',
    converter: Converter({ from: 'cn', to: 'jp' }),
    legal: new Set('体与云个台准于占里游干伙携进万发当回'),
  },
];

/**
 * 兜底简繁异形字集合（zh 语料未用到、但保持拦截能力的字形）。
 * zh.json 新增文案若用到这些字，zh-TW/ja 复制残留时依然可拦截。
 */
const LEGACY_SIMPLIFIED_GLYPHS =
  '设发过这见样为实处与关历广卫组单号乡争办队传约员结据线红纸经继严业产长车声压条张华观团记忆语认识讲课专项级联词买卖双对错时间现点营让请询论证谈该谁调计划开览选权础码库还边个东说话给觉复环变习额题态视页体举尘当惊亲务减测网场帮协阶断写读伟伪汉归问阳阴际险隐顶项顾显风飞马验鸟鸡钟层齐参击势转辆轻较汇纤纪细绳维绿讨训评试资赞针钢钥钱铁银链锁';

function walk(node, collector) {
  if (node && typeof node === 'object') {
    for (const value of Object.values(node)) walk(value, collector);
  } else if (typeof node === 'string') {
    for (const ch of node) {
      if (ch >= '\u3400' && ch <= '\u9fff') collector.add(ch);
    }
  }
}

const zh = JSON.parse(readFileSync(resolve(rootDir, 'locales/zh.json'), 'utf-8'));

const used = new Set();
walk(zh, used);

function collectGlyphs(converter, legal) {
  const glyphs = new Set();
  for (const ch of used) {
    if (legal.has(ch)) continue;
    if (converter(ch) !== ch) glyphs.add(ch);
  }
  for (const ch of LEGACY_SIMPLIFIED_GLYPHS) {
    if (legal.has(ch)) continue;
    if (converter(ch) !== ch) glyphs.add(ch);
  }
  return [...glyphs].sort();
}

const checkOnly = process.argv.includes('--check');
let allFresh = true;

for (const target of TARGETS) {
  const sorted = collectGlyphs(target.converter, target.legal);
  const outputPath = resolve(__dirname, target.output);
  const generated = sorted.join('');

  if (checkOnly) {
    let current = '';
    try {
      current = readFileSync(outputPath, 'utf-8');
    } catch {
      // fall through to mismatch
    }
    if (current === generated) {
      console.log(`${target.name} 集合最新：${sorted.length} 个简体独有字形，与 zh.json 语料同步`);
    } else {
      console.error(
        `${target.name} 集合过期：zh.json 语料已更新，请重跑 bun scripts/generate-simplified-glyphs.mjs`,
      );
      allFresh = false;
    }
  } else {
    writeFileSync(outputPath, generated);
    console.log(
      `${target.name} 生成完成：zh 语料 ${used.size} 个汉字，简体独有字形 ${sorted.length} 个（豁免 ${target.legal.size} 个合法字）`,
    );
  }
}

if (checkOnly && !allFresh) {
  process.exit(1);
}
