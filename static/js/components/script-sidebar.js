// ====== 剧本目录树（幕→场）======

const ScriptSidebar = {
  actData: [],
  collapsedActs: {},

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;
    // 目录树一次取回（幕+场），替代逐幕请求
    const tree = await api.project.tree(projectId);
    this.actData = tree?.acts || [];
    // 游离歌曲（仅音乐剧）
    this.floatingSongs = AppState.currentProject?.project_type === 'musical'
      ? await api.floatingSong.list(projectId) : [];
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

    // 游离歌曲区块（仅音乐剧）
    if (AppState.currentProject?.project_type === 'musical') {
      html += `<div id="floating-song-section" style="margin-top:16px;border-top:1px solid var(--border-color);padding-top:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;">
          <span style="font-size:13px;color:var(--text-secondary);">🎵 游离歌曲</span>
          <button id="btn-add-floating" title="新建游离歌曲" style="font-size:12px;padding:1px 6px;border:1px dashed var(--border-color);border-radius:4px;background:transparent;cursor:pointer;">+</button>
        </div>`;
      for (const s of (this.floatingSongs || [])) {
        const fsActive = FloatingSongEditor.currentSong?.id === s.id;
        html += `<div class="tree-node" data-type="floating" data-id="${s.id}">`;
        html += `<div class="tree-node-header${fsActive ? ' active' : ''}" data-action="select-floating" data-id="${s.id}">`;
        html += `<span class="toggle hidden">·</span>`;
        html += `<span class="node-title">${escHtml(s.song_title)}</span>`;
        html += `<span class="node-wordcount">${(s.lyrics || []).length} 词</span>`;
        html += `</div></div>`;
      }
      if (!(this.floatingSongs || []).length) {
        html += `<div style="font-size:12px;color:var(--text-muted);padding:2px 8px;">（未使用的曲目/歌曲库，不进正文）</div>`;
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
        FloatingSongEditor.clear();
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
        FloatingSongEditor.clear();
        CardEditor.loadScene(scId);
      });
      el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showScriptContextMenu(e.clientX, e.clientY, 'scene', parseInt(el.dataset.id));
      });
    });

    // 游离歌曲：新建 / 打开 / 右键菜单
    const addFsBtn = container.querySelector('#btn-add-floating');
    if (addFsBtn) {
      addFsBtn.addEventListener('click', async () => {
        const title = await uiPrompt('歌曲名:');
        if (!title) return;
        await api.floatingSong.create({ projectId: AppState.currentProject.id, songTitle: title });
        toast('游离歌曲已创建', 'success');
        this.refresh();
      });
    }
    container.querySelectorAll('[data-action="select-floating"]').forEach(el => {
      el.addEventListener('click', async () => {
        // 先等编辑器加载完（currentSong 就绪）再刷新侧栏高亮
        await FloatingSongEditor.open(parseInt(el.dataset.id));
        this.render();
      });
      el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showFloatingContextMenu(e.clientX, e.clientY, parseInt(el.dataset.id));
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

// ====== 游离歌曲右键菜单与操作 ======
function showFloatingContextMenu(x, y, id) {
  const old = document.querySelector('.context-menu');
  if (old) old.remove();

  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;box-shadow:var(--shadow);z-index:500;min-width:160px;padding:4px;font-size:13px;`;

  const items = [
    { label: '重命名', action: () => renameFloatingSong(id) },
    { label: '挂到某场…', action: () => moveFloatingToScene(id) },
    { label: '删除', action: () => deleteFloatingSong(id), danger: true },
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

async function renameFloatingSong(id) {
  const name = await uiPrompt('新歌曲名:');
  if (!name) return;
  await api.floatingSong.update(id, { songTitle: name });
  ScriptSidebar.refresh();
  if (FloatingSongEditor.currentSong?.id === id) FloatingSongEditor.open(id);
}

async function deleteFloatingSong(id) {
  if (!await uiConfirm('删除这首游离歌曲吗？其唱词将一并删除，且不可恢复。', { danger: true, okText: '删除' })) return;
  await api.floatingSong.delete(id);
  toast('已删除');
  if (FloatingSongEditor.currentSong?.id === id) FloatingSongEditor.clear();
  ScriptSidebar.refresh();
}

async function moveFloatingToScene(id) {
  // 按幕分组的场选择弹窗
  const options = [];
  for (const a of (ScriptSidebar.actData || [])) {
    for (const sc of (a.scenes || [])) options.push({ id: sc.id, label: `${a.title} / ${sc.title}` });
  }
  if (!options.length) { toast('请先创建幕和场', 'error'); return; }

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" style="min-width:360px;">
      <h3>挂到某场</h3>
      <div class="form-group">
        <label>选择目标场（歌曲将作为该场的正文歌曲）</label>
        <select id="fs-target-scene" style="width:100%;">
          ${options.map(o => `<option value="${o.id}">${escHtml(o.label)}</option>`).join('')}
        </select>
      </div>
      <div class="modal-actions">
        <button class="btn-cancel">取消</button>
        <button class="btn-primary" id="fs-do-move">确定</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector('#fs-do-move').onclick = async () => {
    const sceneId = parseInt(overlay.querySelector('#fs-target-scene').value);
    overlay.remove();
    try {
      await api.floatingSong.moveToScene(id, sceneId);
      toast('已挂到场，成为正文歌曲');
      if (FloatingSongEditor.currentSong?.id === id) FloatingSongEditor.clear();
      ScriptSidebar.refresh();
      if (AppState.currentScene?.id === sceneId) CardEditor.loadScene(sceneId);
    } catch (err) {
      toast('转换失败: ' + err.message, 'error');
    }
  };
}
