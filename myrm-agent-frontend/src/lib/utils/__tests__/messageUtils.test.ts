import {
  stripDatetimeTag,
  stripMarkdown,
  stripUiActionPayload,
  stripUserMessageDisplayText,
  splitUserMessageForComposer,
  parseExplicitSkillActivation,
  buildExplicitSkillWireMessage,
  formatSkillChipLabel,
  getBrowserTimezone,
  type ExplicitSkillActivation,
} from '../messageUtils';

/** The harness grammar's `MAX_REFERENCE_LIST_CHARS`: the web parse and the agent must agree on what is a tag. */
const MAX_REFERENCE_LIST_CHARS = 1_024;

describe('stripDatetimeTag', () => {
  it('removes current_datetime tags', () => {
    const input = '<current_datetime>2026-05-27T14:00:00Z</current_datetime>Hello world';
    expect(stripDatetimeTag(input)).toBe('Hello world');
  });

  it('handles text without tags', () => {
    expect(stripDatetimeTag('plain text')).toBe('plain text');
  });

  it('handles empty string', () => {
    expect(stripDatetimeTag('')).toBe('');
  });

  it('removes multiple tags', () => {
    const input = '<current_datetime>t1</current_datetime>A<current_datetime>t2</current_datetime>B';
    expect(stripDatetimeTag(input)).toBe('AB');
  });
});

describe('stripUiActionPayload', () => {
  it('removes ui_action_data block from user message', () => {
    const input = '已提交\n操作: 提交\n<ui_action_data>{"type":"ui_action"}</ui_action_data>';
    expect(stripUiActionPayload(input)).toBe('已提交\n操作: 提交');
  });
});

describe('stripUserMessageDisplayText', () => {
  it('removes datetime tag and ui_action payload', () => {
    const input = '<current_datetime>t</current_datetime>已提交\n<ui_action_data>{"type":"ui_action"}</ui_action_data>';
    expect(stripUserMessageDisplayText(input)).toBe('已提交');
  });

  it('removes explicit skill wire prefix', () => {
    const input = '[use daily_report_skill] generate today report';
    expect(stripUserMessageDisplayText(input)).toBe('generate today report');
  });

  it('removes bundle skill prefix and instruction', () => {
    const input = '[use write_report_skill,send_feishu_skill] [instruction: be concise] 生成本周报告';
    expect(stripUserMessageDisplayText(input)).toBe('生成本周报告');
  });

  it('keeps a prefix whose list is over the limit as ordinary text, as the agent reads it', () => {
    const input = `[use ${'a'.repeat(MAX_REFERENCE_LIST_CHARS + 1)}] generate today report`;
    expect(stripUserMessageDisplayText(input)).toBe(input);
  });
});

type ParseCase = [name: string, text: string, expected: ExplicitSkillActivation | null];

/** What the agent's `parse_use_tag` makes of the start of a message: a tag with its names and text, or ordinary text. */
const TAG_CASES: ParseCase[] = [
  ['trims the text behind the tag', '[use a] go  ', { skillNames: ['a'], instruction: null, userText: 'go' }],
  [
    'keeps a multi-line text whole',
    '[use a] line1\nline2',
    { skillNames: ['a'], instruction: null, userText: 'line1\nline2' },
  ],
  [
    'takes any whitespace after the keyword and around the names',
    '[use\n\t a , b ] go',
    { skillNames: ['a', 'b'], instruction: null, userText: 'go' },
  ],
  [
    'takes hyphenated names',
    '[use my-skill,other-skill] go',
    { skillNames: ['my-skill', 'other-skill'], instruction: null, userText: 'go' },
  ],
  ['ignores a tag that is not at the start', 'note\n[use a] go', null],
  ['ignores a list without a name', '[use , ,] go', null],
  ['reads the keyword in lower case only', '[USE a] go', null],
  ['wants whitespace after the keyword', '[user] hello', null],
];

const UNCLOSED_INSTRUCTION = `[instruction:${' '.repeat(64_000)}x`;

/** A long run of whitespace with no closing bracket after it, at both places in the tag where one can sit. */
const FLOOD_CASES: ParseCase[] = [
  ['after the keyword', `[use${' '.repeat(64_000)}`, null],
  [
    'after the instruction marker',
    `[use a] ${UNCLOSED_INSTRUCTION}`,
    { skillNames: ['a'], instruction: null, userText: UNCLOSED_INSTRUCTION },
  ],
];

describe('parseExplicitSkillActivation', () => {
  it('parses single skill activation', () => {
    expect(parseExplicitSkillActivation('[use daily_report_skill] hello')).toEqual({
      skillNames: ['daily_report_skill'],
      instruction: null,
      userText: 'hello',
    });
  });

  it('parses bundle with instruction', () => {
    expect(parseExplicitSkillActivation('[use a_skill,b_skill] [instruction: json] run')).toEqual({
      skillNames: ['a_skill', 'b_skill'],
      instruction: 'json',
      userText: 'run',
    });
  });

  it.each(TAG_CASES)('%s', (_name, text, expected) => {
    expect(parseExplicitSkillActivation(text)).toEqual(expected);
  });

  it('reads a list at the limit as a tag and one character more as ordinary text', () => {
    const atLimit = 'a'.repeat(MAX_REFERENCE_LIST_CHARS);
    expect(parseExplicitSkillActivation(`[use ${atLimit}] go`)?.skillNames).toEqual([atLimit]);
    expect(parseExplicitSkillActivation(`[use ${atLimit}a] go`)).toBeNull();
  });

  it('accepts non-ASCII skill names like the agent does', () => {
    expect(parseExplicitSkillActivation('[use 日报,周报] [instruction: 简短] 写本周总结')).toEqual({
      skillNames: ['日报', '周报'],
      instruction: '简短',
      userText: '写本周总结',
    });
  });

  it.each(FLOOD_CASES)('reads a flood of whitespace %s in linear time', (_where, text, expected) => {
    // CPU time, not wall-clock: a busy machine stretches the latter without the pattern doing more work. A linear scan
    // takes well under 1 ms; adjacent quantifiers that claim the same characters take hundreds of ms (bounded) to
    // seconds.
    const before = process.cpuUsage();
    const parsed = parseExplicitSkillActivation(text);
    const { user, system } = process.cpuUsage(before);
    expect(parsed).toEqual(expected);
    expect((user + system) / 1000).toBeLessThan(50);
  });
});

describe('buildExplicitSkillWireMessage', () => {
  it('builds wire message from pending activation', () => {
    expect(buildExplicitSkillWireMessage({ skillNames: ['a_skill', 'b_skill'], instruction: 'brief' }, 'do work')).toBe(
      '[use a_skill,b_skill] [instruction: brief] do work',
    );
  });
});

type ComposerSplitCase = [name: string, wire: string, expected: ReturnType<typeof splitUserMessageForComposer>];

/** What the composer holds after a stored user message is given back: its text and, apart from it, the skill chip. */
const COMPOSER_SPLIT_CASES: ComposerSplitCase[] = [
  ['takes plain text as it is', 'plain text', { text: 'plain text', activation: null }],
  [
    'splits a skill tag from its text',
    '[use daily_report_skill] generate today report',
    { text: 'generate today report', activation: { skillNames: ['daily_report_skill'], instruction: null } },
  ],
  [
    'keeps the instruction on the chip, not in the text',
    '[use write_report_skill,send_feishu_skill] [instruction: be concise] 生成本周报告',
    {
      text: '生成本周报告',
      activation: { skillNames: ['write_report_skill', 'send_feishu_skill'], instruction: 'be concise' },
    },
  ],
  [
    'gives an empty text for a tag without one',
    '[use writer_skill]',
    {
      text: '',
      activation: { skillNames: ['writer_skill'], instruction: null },
    },
  ],
  [
    'gives an empty text, not the instruction, for a tag with an instruction only',
    '[use writer_skill] [instruction: only this]',
    { text: '', activation: { skillNames: ['writer_skill'], instruction: 'only this' } },
  ],
];

describe('splitUserMessageForComposer', () => {
  it.each(COMPOSER_SPLIT_CASES)('%s', (_name, wire, expected) => {
    const split = splitUserMessageForComposer(wire);

    expect(split).toEqual(expected);
    // Sending what the composer now holds reproduces the stored message byte for byte.
    expect(split.activation ? buildExplicitSkillWireMessage(split.activation, split.text) : split.text).toBe(wire);
  });
});

describe('formatSkillChipLabel', () => {
  it('strips _skill suffix and underscores', () => {
    expect(formatSkillChipLabel('daily_report_skill')).toBe('daily report');
  });
});

describe('stripMarkdown', () => {
  it('removes inline code', () => {
    expect(stripMarkdown('fix `utils.ts` bug')).toBe('fix  bug');
  });

  it('removes code blocks', () => {
    const md = 'before\n```ts\nconst x = 1;\n```\nafter';
    expect(stripMarkdown(md)).toBe('before\nafter');
  });

  it('removes bold and italic markers', () => {
    expect(stripMarkdown('use **bold** and *italic*')).toBe('use bold and italic');
  });

  it('converts links to text', () => {
    expect(stripMarkdown('see [docs](https://example.com)')).toBe('see docs');
  });

  it('removes image syntax', () => {
    expect(stripMarkdown('![alt](image.png) text')).toBe('text');
  });

  it('removes heading markers', () => {
    expect(stripMarkdown('## Title\ncontent')).toBe('Title\ncontent');
  });

  it('removes thinking/reasoning blocks', () => {
    const md = '<think>internal reasoning</think>visible text';
    expect(stripMarkdown(md)).toBe('visible text');
  });

  it('removes REASONING_SCRATCHPAD blocks', () => {
    const md = '<REASONING_SCRATCHPAD>thinking</REASONING_SCRATCHPAD>result';
    expect(stripMarkdown(md)).toBe('result');
  });

  it('removes citation tags', () => {
    expect(stripMarkdown('text<citation id="1"></citation> more')).toBe('text more');
  });

  it('removes blockquote markers', () => {
    expect(stripMarkdown('> quoted text')).toBe('quoted text');
  });

  it('removes list markers', () => {
    expect(stripMarkdown('- item one')).toBe('item one');
    expect(stripMarkdown('* item two')).toBe('item two');
    expect(stripMarkdown('+ item three')).toBe('item three');
  });

  it('removes ordered list markers', () => {
    expect(stripMarkdown('1. first\n2. second')).toBe('first\nsecond');
  });

  it('removes table syntax', () => {
    const md = '| col1 | col2 |\n|---|---|\ntext';
    expect(stripMarkdown(md)).toBe('text');
  });

  it('collapses multiple newlines', () => {
    expect(stripMarkdown('a\n\n\n\nb')).toBe('a\nb');
  });

  it('handles empty string', () => {
    expect(stripMarkdown('')).toBe('');
  });

  it('handles plain text without markdown', () => {
    expect(stripMarkdown('just plain text')).toBe('just plain text');
  });

  it('handles combined markdown and datetime tag cleanup', () => {
    const input = '<current_datetime>2026-05-27</current_datetime>fix `bug` in **module**';
    const cleaned = stripMarkdown(stripDatetimeTag(input));
    expect(cleaned).toBe('fix  in module');
  });
});

describe('getBrowserTimezone', () => {
  it('returns a valid timezone string', () => {
    const tz = getBrowserTimezone();
    expect(typeof tz).toBe('string');
    expect(tz.length).toBeGreaterThan(0);
  });
});
