import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

export function formatCodeSpacing(text, filename) {
  const source = ts.createSourceFile(filename, text, ts.ScriptTarget.Latest, true);
  const edits = [];
  const imports = source.statements.filter(ts.isImportDeclaration);
  const lastImport = imports.at(-1);

  if (lastImport) {
    const remaining = text.slice(lastImport.end);
    const whitespace = remaining.match(/^\s*/)[0];

    if (remaining.trim() && !/\r?\n[\t ]*\r?\n/.test(whitespace)) {
      edits.push({ start: lastImport.end, end: lastImport.end + whitespace.length, text: '\n\n' });
    }
  }

  function visit(node) {
    if (ts.isBlock(node)) {
      node.statements.forEach((statement, index) => {
        if (!ts.isReturnStatement(statement) || !statement.expression || index === 0) {
          return;
        }

        let expression = statement.expression;

        while (ts.isParenthesizedExpression(expression)) {
          expression = expression.expression;
        }

        if (
          !ts.isJsxElement(expression) &&
          !ts.isJsxSelfClosingElement(expression) &&
          !ts.isJsxFragment(expression)
        ) {
          return;
        }

        const previous = node.statements[index - 1];
        const gap = text.slice(previous.end, statement.getStart(source));

        if (!/\r?\n[\t ]*\r?\n/.test(gap)) {
          // Keep comments and indentation; Prettier aligns the return afterward.
          edits.push({ start: previous.end, end: previous.end, text: '\n\n' });
        }
      });
    }

    ts.forEachChild(node, visit);
  }

  visit(source);

  for (const edit of edits.sort((a, b) => b.start - a.start)) {
    text = text.slice(0, edit.start) + edit.text + text.slice(edit.end);
  }

  return text;
}

async function sourceFiles(directory) {
  const files = [];

  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);

    if (entry.isDirectory()) {
      files.push(...(await sourceFiles(filename)));
    } else if (/\.[cm]?[jt]sx?$/.test(entry.name)) {
      files.push(filename);
    }
  }

  return files;
}

async function main() {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const check = process.argv.includes('--check');
  let failed = false;

  for (const filename of await sourceFiles(path.join(root, 'src'))) {
    const original = await readFile(filename, 'utf8');
    const formatted = formatCodeSpacing(original, filename);

    if (original === formatted) {
      continue;
    }

    if (check) {
      console.error(
        `${path.relative(root, filename)}: add a blank line after imports or before JSX returns`,
      );
      failed = true;
    } else {
      await writeFile(filename, formatted);
    }
  }

  if (failed) {
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await main();
}
