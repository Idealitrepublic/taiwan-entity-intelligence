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

const focusCode = html.slice(html.indexOf('  function focusKnowledgeExpansion('), html.indexOf('  function focusLegacyExpansion('));
const graphSub = {textContent: '12 nodes'};
const focusContext = vm.createContext({
  zoom: .35, panX: 0, panY: 0,
  knowledgeGraph: {nodes: new Map([['bridge',{id:'bridge'}],['child',{id:'child'}]]), edges: new Map([['edge',{source:'bridge',target:'child'}]])},
  fitGraphBounds() {this.zoom=.35;}, readableLegacyZoom:()=>1.6,
  knowledgeMetrics:()=>({halfWidth:95}),
  knowledgePositions:()=>new Map([['bridge',{x:500,y:350}],['child',{x:900,y:350}]]),
  graphFitArea:()=>({x:50,y:70,width:900,height:560}),
  setZoom(value) {focusContext.zoom=value;}, applyGraphTransform:()=>{}, $:()=>graphSub,
});
vm.runInContext(focusCode+'\nfocusKnowledgeExpansion("bridge");',focusContext);
assert.equal(focusContext.zoom,2.08,'expansion retains readable labels rather than fitting 12 nodes into tiny text');
assert(Number.isFinite(focusContext.panX)&&Number.isFinite(focusContext.panY));
assert.match(graphSub.textContent,/Fit for the full graph/);
assert(html.includes("if(entityId===state.rootId&&!continuing&&graphMode!=='path')fitGraphBounds();else focusKnowledgeExpansion(entityId)"),'initial overview stays fully visible; user expansion focuses the readable branch');
console.log('PASS expanded published graph keeps readable branch zoom; manual zoom remains unrestricted');

const parentLeft=500+focusContext.panX+(500-500)*focusContext.zoom-95*focusContext.zoom;
assert(parentLeft>=74,'expanded branch keeps the clicked node and its label inside the canvas left padding');
console.log('PASS automatic branch focus does not clip the expanded parent label');

focusContext.knowledgePositions=()=>new Map([['bridge',{x:500,y:350}],['child',{x:100,y:350}]]);
vm.runInContext('focusKnowledgeExpansion("bridge");',focusContext);
const parentRight=500+focusContext.panX+95*focusContext.zoom;
assert(parentRight<=926,'expanding a node with only left neighbors also preserves its right label boundary');
