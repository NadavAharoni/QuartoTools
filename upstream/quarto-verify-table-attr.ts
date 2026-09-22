/* Verify that a table's pandoc identifier survives the visual editor's
   read/write round-trip. Drives the two patched functions directly with fakes,
   so it needs no DOM, no pandoc process and no editor instance.

   Run:  node_modules/.bin/tsx verify-table-attr.ts     (from the repo root)
*/
/* eslint-disable @typescript-eslint/no-explicit-any */

import { readPandocTable, writePandocTableContainer } from './packages/editor/src/nodes/table/table-pandoc';

// ---------------------------------------------------------------- read side

// A pandoc Table token: [ attr, caption, colspecs, head, bodies, foot ].
// attr is [ id, classes, keyvalues ] -- here the crossref label.
const tableToken: any = {
  t: 'Table',
  c: [
    ['tbl-nums', [], []],                    // 0 attr
    [null, []],                              // 1 caption (short, full)
    [],                                      // 2 colspecs
    [['', [], []], []],                      // 3 head (attr, rows)
    [[['', [], []], 0, [], []]],             // 4 bodies
    [['', [], []], []],                      // 5 foot
  ],
};

const schema: any = {
  nodes: {
    table_container: 'table_container',
    table: 'table',
    table_row: 'table_row',
    table_header: 'table_header',
    table_cell: 'table_cell',
  },
};

const opened: Array<{ type: string; attrs: any }> = [];
const writer: any = {
  openNode: (type: string, attrs: any) => opened.push({ type, attrs }),
  closeNode: () => undefined,
  writeTokens: () => undefined,
};

readPandocTable(schema)(writer, tableToken);

const container = opened.find(n => n.type === 'table_container');
const readId = container?.attrs?.id ?? null;

// --------------------------------------------------------------- write side

const node: any = {
  attrs: { id: 'tbl-nums', classes: [], keyvalue: [] },
  firstChild: { type: 'table' },
  lastChild: { type: 'table_caption' },
};

let writtenAttr: any[] = [];
const output: any = {
  writeToken: (_t: unknown, fn?: () => void) => fn && fn(),
  writeAttr: (...args: any[]) => { writtenAttr = args; },
  writeNode: () => undefined,
  writeArray: (fn: () => void) => fn(),
  write: () => undefined,
  writeInlines: () => undefined,
};

writePandocTableContainer(output, node);

// ------------------------------------------------------------------ results

const readOk = readId === 'tbl-nums';
const writeOk = writtenAttr[0] === 'tbl-nums';

console.log(`read  : table_container attrs.id = ${JSON.stringify(readId)}  ${readOk ? 'PASS' : 'FAIL'}`);
console.log(`write : writeAttr(${writtenAttr.map(a => JSON.stringify(a)).join(', ')})  ${writeOk ? 'PASS' : 'FAIL'}`);
console.log(readOk && writeOk
  ? 'RESULT: identifier survives the round-trip'
  : 'RESULT: identifier is LOST');

process.exit(readOk && writeOk ? 0 : 1);
