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
const focusContext = vm.createContext({
  zoom: 1, panX: 0, panY: 0,
  knowledgeGraph: {nodes: new Map([['bridge',{id:'bridge'}]])},
  knowledgeMetrics:()=>({halfWidth:45,top:45,bottom:22}),
  syncGraphCanvasTop:()=>{},
  graphFitArea:()=>({x:50,y:70,width:900,height:560}),
  setZoom(value) {focusContext.zoom=value;}, applyGraphTransform:()=>{},
  newIds:new Set(['child']),
  layout:{positions:new Map([['bridge',{x:500,y:350}]]),zones:[{ids:['child'],left:600,right:780,top:280,bottom:410}]},
});
vm.runInContext(focusCode+'\nfocusKnowledgeExpansion("bridge",layout,newIds);',focusContext);
assert.equal(focusContext.zoom,1,'local expansion keeps the current scale when the branch fits');
assert.equal(focusContext.panX,0,'the camera stays put when the new group is visible');
assert.equal(focusContext.panY,0);
focusContext.layout.zones[0]={ids:['child'],left:840,right:980,top:280,bottom:410};
vm.runInContext('focusKnowledgeExpansion("bridge",layout,newIds);',focusContext);
assert.equal(focusContext.zoom,1,'no global zoom-out for a group just beyond the canvas');
assert.equal(focusContext.panX,-30,'pan only the distance needed to reveal the group');
assert.equal(focusContext.panY,0);
assert(html.includes("focusKnowledgeExpansion(entityId,layout,newIds)"));
console.log('PASS expansion preserves the camera and pans minimally to reveal a nearby group');
