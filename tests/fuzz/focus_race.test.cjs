/** Minimized sequence from seed 20261118: focus → immediately select a node. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const line=fs.readFileSync('web/index.html','utf8').split('\n').find(l=>l.trim().startsWith("graphFocus.addEventListener('click'"));
const callbacks=[];
const context=vm.createContext({
 graphFocus:{textContent:'',setAttribute(){},addEventListener:(_,f)=>context.activate=f},
 document:{querySelector:()=>({classList:{toggle:()=>true}})},
 requestAnimationFrame:cb=>callbacks.push(cb),placeConnectionSummary:()=>{},
 cameraRestored:0,restoreGraphCamera:()=>context.cameraRestored++,
 selected:null,infoHidden:true,resetGraphView:()=>{context.selected=null;context.infoHidden=true}
});
vm.runInContext(line,context);context.activate();
context.selected='newly-selected-node';context.infoHidden=false;
callbacks.forEach(cb=>cb());
assert.equal(context.selected,'newly-selected-node','A delayed focus reset erased a later node selection');
assert.equal(context.cameraRestored,1,'Focus schedules a camera-only restore');
assert.equal(context.infoHidden,false,'A delayed focus reset closed the node inspector');
console.log('PASS focus → select: no stale deferred reset closes a newer inspector');
