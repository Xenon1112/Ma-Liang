// ====== 扩展点消费逻辑:sidebar.tabs / toolbar.actions ======
// 依赖 nw.js(注册表),须在 nw.js 之后、app.js 之前加载
//
// sidebar.tabs 注册形状:{id, title, order, refresh()}
//   - id:tab 标识(data-tab 值);title:标签文字;order:排序(小在前);refresh():切换到该 tab 时调用,组件自行渲染进 #panel-content
// toolbar.actions 注册形状:{id, label, title, onClick, order?, container?, before?, closeIfOpen?()}
//   - label:按钮文字;title:tooltip;order:同锚点内的排序;container:目标容器选择器(默认 .toolbar-left);
//     before:静态按钮 id,插到它前面(缺省则追加到 container 末尾);
//     closeIfOpen:可选,Esc 时调用,若关闭了浮层返回 true(如搜索面板)

// 根据注册清单动态生成右侧栏 tab 按钮(幂等:先清掉旧的动态 tab)
function renderSidebarTabs() {
  const tabsBar = document.querySelector('.panel-tabs');
  if (!tabsBar) return;
  const collapseBtn = document.getElementById('btn-collapse-right');
  tabsBar.querySelectorAll('.panel-tab').forEach(t => t.remove());

  const tabs = NW.getComponents('sidebar.tabs').slice().sort((a, b) => (a.order || 0) - (b.order || 0));
  const active = AppState.rightPanelTab || (tabs[0] && tabs[0].id);
  for (const tab of tabs) {
    const el = document.createElement('div');
    el.className = 'panel-tab' + (tab.id === active ? ' active' : '');
    el.dataset.tab = tab.id;
    el.textContent = tab.title;
    el.addEventListener('click', () => {
      AppState.rightPanelTab = tab.id;
      switchRightTab(tab.id);
    });
    tabsBar.insertBefore(el, collapseBtn);
  }
}

// 根据注册清单动态生成工具栏按钮
function renderToolbarActions() {
  const actions = NW.getComponents('toolbar.actions').slice().sort((a, b) => (a.order || 0) - (b.order || 0));
  for (const action of actions) {
    const btn = document.createElement('button');
    btn.className = 'toolbar-btn';
    btn.id = `btn-${action.id}`;
    btn.textContent = action.label;
    if (action.title) btn.title = action.title;
    btn.addEventListener('click', () => action.onClick());

    const anchor = action.before && document.getElementById(action.before);
    if (anchor) {
      anchor.parentNode.insertBefore(btn, anchor);
    } else {
      const container = document.querySelector(action.container || '.toolbar-left');
      if (container) container.appendChild(btn);
    }
  }
}

// 切换右侧面板标签(供 app.js 与插件组件调用)
function switchRightTab(tabName) {
  // 展开面板
  setRightPanelCollapsed(false);

  // 更新标签高亮
  document.querySelectorAll('.panel-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabName);
  });

  // 刷新对应内容
  AppState.rightPanelTab = tabName;
  const tab = NW.getComponents('sidebar.tabs').find(t => t.id === tabName);
  if (tab && typeof tab.refresh === 'function') tab.refresh();
}
