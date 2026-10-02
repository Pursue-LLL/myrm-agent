// eslint-disable-next-line no-control-regex -- \x00C{n}\x00 为代码槽占位符契约（本模块生成并回填，非任意控制字符匹配）
const CODE_SLOT_RE = /\x00C(\d+)\x00/g;

/** Extract fenced and inline code so citation parsing skips literal `[N]` inside code. */
export const maskCodeRegions = (markdown: string): { text: string; slots: string[] } => {
  const slots: string[] = [];
  let slotIndex = 0;

  const pushSlot = (block: string): string => {
    slots.push(block);
    const token = `\x00C${slotIndex}\x00`;
    slotIndex += 1;
    return token;
  };

  let text = markdown.replace(/(^|\n)(`{3,}|~{3,})[^\n]*(?:\n[\s\S]*?\n\2(?=\n|$)|[\s\S]*$)/gm, (block) =>
    pushSlot(block),
  );

  text = text.replace(/(`+)[^`\n]+?\1/g, (block) => pushSlot(block));

  return { text, slots };
};

export const unmaskCodeRegions = (markdown: string, slots: string[]): string =>
  markdown.replace(CODE_SLOT_RE, (_match, indexText: string) => {
    const index = Number.parseInt(indexText, 10);
    return slots[index] ?? '';
  });
