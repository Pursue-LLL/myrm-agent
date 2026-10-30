// What the TypeScript compiler's own syntax tree says the code graph holds for each file.
//
// Run by check_code_graph_js_ts_accuracy.py, which compares it with the tree-sitter extractor:
//   node code_graph_ts_reference.mjs <typescript package directory>   (files as JSON on stdin)
// stdin:  [{"path": "<relative path>", "module": "<dotted module name>", "source": "<text>"}, ...]
// stdout: one JSON object per file with the symbols, calls and class inheritances the extractor's rules produce.
//
// The rules restate js_ts_extractor.py on the compiler's tree: named functions, classes and methods are symbols;
// a call is recorded for a plain or member callee and belongs to the innermost open named definition that is not
// a class; a call written in front of a definition's own name (a decorator) is outside that definition.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const ts = createRequire(import.meta.url)(process.argv[2]);
const K = ts.SyntaxKind;

const FUNCTION_VALUES = new Set([K.ArrowFunction, K.FunctionExpression]);

const isMemberName = (name) => ts.isIdentifier(name) || ts.isPrivateIdentifier(name);

/** Identifier or member chain as written; what stands left of a base that is not a plain name is dropped. */
function dottedName(node) {
  const parts = [];
  for (;;) {
    if (ts.isIdentifier(node)) {
      parts.push(node.text);
      break;
    }
    if (node.kind === K.ThisKeyword) {
      parts.push("this");
      break;
    }
    if (ts.isNonNullExpression(node)) {
      node = node.expression;
      continue;
    }
    if (!ts.isPropertyAccessExpression(node)) break;
    parts.push(node.name.text);
    node = node.expression;
  }
  return parts.reverse().join(".");
}

function extract({ path, module, source }) {
  const sf = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true);
  const line = (position) => sf.getLineAndCharacterOfPosition(position).line + 1;
  const symbols = [];
  const calls = [];
  const inheritances = [];
  const scopes = [];

  const enclosing = (position, skipClasses) => {
    for (let i = scopes.length - 1; i >= 0; i--) {
      const scope = scopes[i];
      if (scope.start <= position && !(skipClasses && scope.isClass)) return scope.name;
    }
    return null;
  };

  const recordInheritance = (classNode, subType, at) => {
    for (const clause of classNode.heritageClauses ?? []) {
      if (clause.token !== K.ExtendsKeyword) continue;
      const base = dottedName(clause.types[0].expression);
      if (base) inheritances.push([subType, base, at]);
    }
  };

  const define = (extent, nameNode, kind) => {
    const start = nameNode.getStart(sf);
    const qualified = `${enclosing(start, false) ?? module}.${nameNode.getText(sf)}`;
    symbols.push([qualified, kind, line(start), line(extent.getEnd())]);
    if (kind === "class") recordInheritance(extent, qualified, line(start));
    scopes.push({ name: qualified, start, isClass: kind === "class" });
    return true;
  };

  /** Opens the scope of a named definition and returns true; anything else defines nothing. */
  const openDefinition = (node) => {
    if (ts.isFunctionDeclaration(node)) return node.name && node.body ? define(node, node.name, "function") : false;
    if (ts.isClassDeclaration(node)) return node.name ? define(node, node.name, "class") : false;
    if (ts.isVariableDeclaration(node)) {
      const value = node.initializer;
      if (!ts.isIdentifier(node.name) || !value) return false;
      if (FUNCTION_VALUES.has(value.kind)) return define(value, node.name, "function");
      return ts.isClassExpression(value) ? define(value, node.name, "class") : false;
    }
    if (!node.parent || !ts.isClassLike(node.parent)) return false;
    if (ts.isMethodDeclaration(node) || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)) {
      return node.body && isMemberName(node.name) ? define(node, node.name, "method") : false;
    }
    if (ts.isConstructorDeclaration(node)) {
      const keyword = node.body && node.getChildren(sf).find((child) => child.kind === K.ConstructorKeyword);
      return keyword ? define(node, keyword, "method") : false;
    }
    if (ts.isPropertyDeclaration(node)) {
      const value = node.initializer;
      return value && FUNCTION_VALUES.has(value.kind) && isMemberName(node.name) ? define(node, node.name, "method") : false;
    }
    return false;
  };

  const recordCall = (node) => {
    const callee = node.expression;
    if (!ts.isIdentifier(callee) && !ts.isPropertyAccessExpression(callee)) return;
    const calledName = ts.isPropertyAccessExpression(callee) ? callee.name : callee;
    const position = calledName.getStart(sf);
    calls.push([line(position), dottedName(callee), enclosing(position, true) ?? module, node.arguments?.length ?? 0]);
  };

  const visit = (node) => {
    const opened = openDefinition(node);
    if (ts.isCallExpression(node) || ts.isNewExpression(node)) recordCall(node);
    ts.forEachChild(node, visit);
    if (opened) scopes.pop();
  };

  visit(sf);
  return { path, symbols, calls, inheritances };
}

for (const request of JSON.parse(readFileSync(0, "utf8"))) {
  let result;
  try {
    result = extract(request);
  } catch (error) {
    result = { path: request.path, error: String(error) };
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
}
