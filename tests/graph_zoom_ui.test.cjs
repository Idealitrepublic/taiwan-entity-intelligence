const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('web/index.html', 'utf8');
const line = html.split('\n').find(row => row.trimStart().startsWith('function setZoom('));
assert(line, 'shipped graph zoom handler exists');
const indicator = {textContent: ''};
const context = vm.createContext({zoom: 1.2, expandedHub: 'related',
  $: id => id === 'zoomValue' ? indicator : null,
  applyGraphTransform: () => {}});
vm.runInContext(`${line}\nsetZoom(.35);`, context);
assert.equal(context.zoom, .35, 'expanded related company graph permits zooming out');
assert.equal(indicator.textContent, '35%');
vm.runInContext('setZoom(.001);', context);
assert.equal(context.zoom, .05, 'tiny zoom is bounded but not forced to readable expansion zoom');
assert.match(html, /這家公司連結了什麼 \/ Relationship summary/);
console.log('PASS related-company zoom and dashboard relationship summary');
