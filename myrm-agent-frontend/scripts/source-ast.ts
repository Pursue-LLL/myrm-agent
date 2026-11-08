/**
 * 静态门禁共用的语法树入口：用 oxc-parser 解析一份源码，并把节点偏移换算成行号。
 *
 * 门禁只需要逐文件的语法树，不需要类型信息；oxc-parser 与仓库已在用的 oxlint 同属 oxc 工具链，
 * 节点是 ESTree 加 JSX / TS 扩展，类型由同一个包导出。
 */
import { type JSXAttributeName, type JSXElementName, parseSync, type Program } from 'oxc-parser';

/** 与 TypeScript 的换行口径一致：`\r\n`、`\n`、`\r`、U+2028、U+2029。 */
const LINE_BREAK = /\r\n|[\n\r\u2028\u2029]/;

/**
 * 解析源码；`.tsx` / `.jsx` 按 JSX 方言，其余按 TS。
 * 语法错误直接抛出：门禁读到半截语法树会静默漏报，宁可让门禁变红。
 */
export function parseProgram(source: string, fileName: string): Program {
  const { program, errors } = parseSync(fileName, source, { lang: fileName.endsWith('x') ? 'tsx' : 'ts' });
  const failure = errors.find((error) => error.severity === 'Error');
  if (failure) {
    throw new Error(`Cannot parse ${fileName}: ${failure.message}`);
  }
  return program;
}

/** 字符偏移所在的行号（从 1 起）。 */
export function lineAt(source: string, offset: number): number {
  return source.slice(0, offset).split(LINE_BREAK).length;
}

/** JSX 标签名或属性名的源码写法：`div`、`Dialog.Trigger`、`xlink:href`。 */
export function jsxNameText(name: JSXElementName | JSXAttributeName): string {
  switch (name.type) {
    case 'JSXIdentifier':
      return name.name;
    case 'JSXNamespacedName':
      return `${name.namespace.name}:${name.name.name}`;
    case 'JSXMemberExpression':
      return `${jsxNameText(name.object)}.${name.property.name}`;
  }
}
