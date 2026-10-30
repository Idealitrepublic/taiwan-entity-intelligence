const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html', 'utf8');
function loadDisplay(context) {
  const line = html.split('\n').find(row => row.includes('const $=id=>'));
  vm.runInContext('const ' + line.slice(line.indexOf('esc='), line.indexOf(',num=')) + ';', context);
  vm.runInContext(html.split('\n').find(row => row.includes('function snapshotTime(')), context);
  vm.runInContext(html.slice(html.indexOf('  const entityTypeLabels='),
    html.indexOf('  const GRAPH_PAGE_SIZE=')), context);
}
module.exports = {html, loadDisplay};
