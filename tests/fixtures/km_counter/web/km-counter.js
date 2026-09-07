// ====== km_counter 总验收测试插件前端 ======
// 覆盖协议承诺的前端表面:挂载点 NW.plugins.<id>、sidebar.tabs / toolbar.actions
// 扩展点注册、NW.events 订阅 project.opened。无头验证见 tests/web_stub_test.js。

NW.plugins.km_counter = {
  openedProjectId: null, // project.opened 订阅记录,便于验收断言

  refresh() {
    const el = document.getElementById('panel-content');
    if (el) el.innerHTML = '<p>km_counter 验收测试 tab</p>';
  },

  onToolbarClick() {
    // 验收按钮:无实际业务操作
  },
};

// 注册右侧栏 tab(消费逻辑见 static/js/core/extensions.js)
NW.registerComponent('sidebar.tabs', {
  id: 'km-counter',
  title: '计数',
  order: 90,
  refresh: () => NW.plugins.km_counter.refresh(),
});

// 注册工具栏按钮(消费逻辑见 static/js/core/extensions.js)
NW.registerComponent('toolbar.actions', {
  id: 'km-counter',
  label: '计数',
  title: 'km_counter 验收测试按钮',
  order: 90,
  onClick: () => NW.plugins.km_counter.onToolbarClick(),
});

// 订阅内核前端事件(事件目录见 docs/插件协议-v0草案.md §6)
NW.events.on('project.opened', (payload) => {
  NW.plugins.km_counter.openedProjectId = payload && payload.projectId;
});
