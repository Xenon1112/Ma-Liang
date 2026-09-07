// 前端扩展点/事件的无头桩测试(node 直接运行,无第三方依赖):
//   node tests/web_stub_test.js
//
// 用 vm 构造最小浏览器环境(window === 全局、AppState 事件总线桩),
// 按真实加载顺序跑 static/js/core/nw.js + static/js/core/extensions.js
// + tests/fixtures/km_counter/web/km-counter.js,断言:
// - NW.registerComponent 注册的 sidebar.tabs / toolbar.actions 内容正确;
// - NW.events 订阅 project.opened 生效。
// DOM 渲染(renderSidebarTabs/renderToolbarActions)依赖真实 document,不在本桩覆盖范围。
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');

const sandbox = {
  console,
  // extensions.js / km-counter.js 在加载期不触碰 document,仅给最小桩
  // (card-editor.js 加载期挂 document 级 keydown 监听,需要 addEventListener 桩)
  document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener: () => {} },
  // AppState 桩:与 static/js/state.js 的事件总线同形状(NW.events 直接指向它)
  AppState: {
    rightPanelTab: null,
    _listeners: {},
    on(event, fn) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(fn);
    },
    emit(event, data) {
      (this._listeners[event] || []).forEach(fn => fn(data));
    },
  },
};
sandbox.window = sandbox; // 浏览器中 window === globalThis,插件经 window.NW / 裸 NW 两种引用都要可达
vm.createContext(sandbox);

let failures = 0;
function check(name, cond, detail) {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${name}` + (!cond && detail ? ` — ${detail}` : ''));
  if (!cond) failures++;
}

for (const rel of [
  'static/js/core/nw.js',
  'static/js/core/extensions.js',
  'tests/fixtures/km_counter/web/km-counter.js',
  'plugins/graph/web/graph.js',
  // script 插件 web 文件依赖 graph 渲染器注册表,须排在 graph.js 之后(与注册表依赖序一致)
  'plugins/script/web/script-sidebar.js',
  'plugins/script/web/card-editor.js',
]) {
  const file = path.join(ROOT, rel);
  vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: rel });
}

const { NW } = sandbox;

// --- sidebar.tabs ---
const tabs = NW.getComponents('sidebar.tabs');
const tab = tabs.find(t => t.id === 'km-counter');
check('sidebar.tabs 已注册 km-counter tab', !!tab, JSON.stringify(tabs));
check('tab 形状完整(id/title/order/refresh)',
  !!tab && tab.title === '计数' && tab.order === 90 && typeof tab.refresh === 'function',
  JSON.stringify(tab));

// --- toolbar.actions ---
const actions = NW.getComponents('toolbar.actions');
const action = actions.find(a => a.id === 'km-counter');
check('toolbar.actions 已注册 km-counter 按钮', !!action, JSON.stringify(actions));
check('按钮形状完整(id/label/title/onClick/order)',
  !!action && action.label === '计数' && typeof action.onClick === 'function' && action.order === 90,
  JSON.stringify(action));

// --- 挂载点与事件订阅 ---
check('插件挂载到 NW.plugins.km_counter', !!NW.plugins.km_counter);
NW.events.emit('project.opened', { projectId: 42, projectType: 'novel' });
check('project.opened 订阅生效',
  NW.plugins.km_counter && NW.plugins.km_counter.openedProjectId === 42,
  `openedProjectId=${NW.plugins.km_counter && NW.plugins.km_counter.openedProjectId}`);

// --- graph 渲染器注册表(地基机制,无 UI 面板) ---
const graph = NW.plugins.graph;
check('graph 前端挂载到 NW.plugins.graph', !!graph);
graph.registerRenderer('km-block', { render(container, node) {} });
check('渲染器注册后可按类型取回',
  typeof graph.getRenderer('km-block').render === 'function');
check('未注册类型取回 null', graph.getRenderer('ghost') === null);
let dupThrew = false;
try {
  graph.registerRenderer('km-block', { render() {} });
} catch (e) {
  dupThrew = true;
}
check('渲染器重复注册抛错', dupThrew);
let noRenderThrew = false;
try {
  graph.registerRenderer('bad', {});
} catch (e) {
  noRenderThrew = true;
}
check('缺 render 的渲染器注册抛错', noRenderThrew);

// --- script 插件前端:挂载点 + window 兼容别名 + 六类型渲染器注册 ---
const script = NW.plugins.script;
check('script 前端挂载 sidebar/cardEditor 子键',
  !!script && !!script.sidebar && !!script.cardEditor);
check('window 兼容别名 ScriptSidebar 指向 NW.plugins.script.sidebar',
  sandbox.window.ScriptSidebar === script.sidebar);
check('window 兼容别名 CardEditor 指向 NW.plugins.script.cardEditor',
  sandbox.window.CardEditor === script.cardEditor);
check('cardEditor 保留 renderCard/_renderCardHtml(分发 + 原实现)',
  typeof script.cardEditor.renderCard === 'function'
  && typeof script.cardEditor._renderCardHtml === 'function');
for (const t of ['action', 'dialogue', 'song', 'lyric', 'ensemble', 'dual']) {
  const r = graph.getRenderer(t);
  check(`script 已注册 ${t} 渲染器`, !!r && typeof r.render === 'function');
}

if (failures) {
  console.log(`\n${failures} 项失败`);
  process.exit(1);
}
console.log('\n前端桩测试全部通过');
