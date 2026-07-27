// ====== 剧本目录树（幕→场）======

const ScriptSidebar = {
  actData: [],
  collapsedActs: {},

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;
    this.actData = await api.act.list(projectId);
    for (const act of this.actData) {
      act.scenes = await api.scene.list(act.id);
    }
    this.render();
  },

  render() {
    const container = document.getElementById('tree-container');
    let html = '';

    for (const act of this.actData) {
      const collapsed = this.collapsedActs[act.id] !== false;
      const actActive = AppState.currentAct?.id === act.id && !AppState.currentScene;

      html += `<div class="tree-node" data-type="act" data-id="${act.id}">`;
      html += `<div class="tree-node-header${actActive ? ' active' : ''}" data-action="select-act" data-id="${act.id}">`;
      html += `<span class="toggle${collapsed ? '' : ' open'}" data-action="toggle-act" data-id="${act.id}">${collapsed ? '▶' : '▼'}</span>`;
      html += `<span class="node-title">🎭 ${escHtml(act.title)}</span>`;
      html += `</div>`;

      if (!collapsed) {
        html += `<div class="tree-node-children">`;
        for (const sc of (act.scenes || [])) {
          const scActive = AppState.currentScene?.id === sc.id;
          html += `<div class="tree-node" data-type="scene" data-id="${sc.id}">`;
          html += `<div class="tree-node-header${scActive ? ' active' : ''}" data-action="select-scene" data-id="${sc.id}" data-act="${act.id}">`;
          html += `<span class="toggle hidden">·</span>`;
          html += `<span class="node-title">${escHtml(sc.title)}</span>`;
          html += `<span class="node-wordcount">${sc.word_count || 0} 字</span>`;
          html += `</div></div>`;
        }
        html += `</div>`;
      }
      html += `</div>`;
    }

    container.innerHTML = html;

    container.querySelectorAll('[data-action="toggle-act"]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const aid = parseInt(el.dataset.id);
        this.collapsedActs[aid] = !(this.collapsedActs[aid] !== false);
        this.render();
      });
    });

    container.querySelectorAll('[data-action="select-act"]').forEach(el => {
      el.addEventListener('click', () => {
        const act = this.actData.find(a => a.id === parseInt(el.dataset.id));
        AppState.currentAct = act;
        AppState.currentScene = null;
        CardEditor.clear();
      });
      el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showScriptContextMenu(e.clientX, e.clientY, 'act', parseInt(el.dataset.id));
      });
    });

    container.querySelectorAll('[data-action="select-scene"]').forEach(el => {
      el.addEventListener('click', async () => {
        const scId = parseInt(el.dataset.id);
        const actId = parseInt(el.dataset.act);
        const act = this.actData.find(a => a.id === actId);
        const sc = act?.scenes?.find(s => s.id === scId);
        AppState.currentAct = act;
        AppState.currentScene = sc;
        CardEditor.loadScene(scId);
      });
      el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showScriptContextMenu(e.clientX, e.clientY, 'scene', parseInt(el.dataset.id));
      });
    });
  },
};

function showScriptContextMenu(x, y, type, id) {
  const old = document.querySelector('.context-menu');
  if (old) old.remove();

  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;box-shadow:var(--shadow);z-index:500;min-width:140px;padding:4px;font-size:13px;`;

  const items = [
    { label: '重命名', action: () => renameScriptItem(type, id) },
    { label: '删除', action: () => deleteScriptItem(type, id), danger: true },
  ];

  menu.innerHTML = items.map(it => `
    <div class="ctx-item" style="padding:6px 12px;border-radius:4px;cursor:pointer;${it.danger?'color:var(--danger)':''}">${it.label}</div>
  `).join('');

  document.body.appendChild(menu);
  menu.querySelectorAll('.ctx-item').forEach((el, i) => {
    el.addEventListener('click', () => { menu.remove(); items[i].action(); });
    el.addEventListener('mouseenter', () => el.style.background = 'var(--bg-hover)');
    el.addEventListener('mouseleave', () => el.style.background = 'transparent');
  });
  setTimeout(() => document.addEventListener('click', function c(e) { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', c); } }), 0);
}

async function renameScriptItem(type, id) {
  const name = await uiPrompt('新名称:');
  if (!name) return;
  if (type === 'act') await api.act.update(id, { title: name });
  else await api.scene.update(id, { title: name });
  ScriptSidebar.refresh();
}

async function deleteScriptItem(type, id) {
  if (!await uiConfirm('确定删除吗？将移入回收站。', { danger: true, okText: '删除' })) return;
  if (type === 'act') await api.act.delete(id);
  else await api.scene.delete(id);
  toast('已移入回收站');
  // 删除的正是当前打开的幕/场时，清空编辑器状态，防止继续写入已删除实体
  if (type === 'act' && AppState.currentAct?.id === id) {
    AppState.currentAct = null;
    AppState.currentScene = null;
    CardEditor.clear();
  } else if (type === 'scene' && AppState.currentScene?.id === id) {
    AppState.currentScene = null;
    CardEditor.clear();
  }
  ScriptSidebar.refresh();
}

async function showAddActModal() {
  const title = await uiPrompt('幕名（如"第一幕"）:');
  if (!title) return;
  await api.act.create({ projectId: AppState.currentProject.id, title });
  toast('幕已创建', 'success');
  ScriptSidebar.refresh();
}

async function showAddSceneModal() {
  const actId = AppState.currentAct?.id;
  if (!actId) { toast('请先选择一个幕', 'error'); return; }
  const title = await uiPrompt('场名（如"第一场"）:');
  if (!title) return;
  await api.scene.create({ actId, projectId: AppState.currentProject.id, title });
  toast('场已创建', 'success');
  ScriptSidebar.refresh();
}
