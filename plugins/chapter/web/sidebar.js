// ====== 目录树 Sidebar ======

NW.plugins.chapter = {
  volumeData: [],
  collapsedVolumes: {},

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;

    // 目录树一次取回（卷+章），替代逐卷请求
    const tree = await api.project.tree(projectId);
    this.volumeData = tree?.volumes || [];

    this.render();
  },

  // 保存后局部更新某章字数（不重取数据、不重渲染整棵树）
  updateWordCount(chapterId, wordCount) {
    for (const vol of this.volumeData) {
      const ch = (vol.chapters || []).find(c => c.id === chapterId);
      if (ch) {
        ch.word_count = wordCount;
        const el = document.querySelector(`.tree-node[data-type="chapter"][data-id="${chapterId}"] .node-wordcount`);
        if (el) el.textContent = wordCount;
        const volEl = document.querySelector(`.tree-node[data-type="volume"][data-id="${vol.id}"] .node-wordcount`);
        if (volEl) volEl.textContent = `${getVolWordCount(vol)} 字`;
        break;
      }
    }
  },

  render() {
    const container = document.getElementById('tree-container');
    let html = '';

    for (const vol of this.volumeData) {
      const isCollapsed = this.collapsedVolumes[vol.id] !== false;
      const volActive = AppState.currentVolume?.id === vol.id && !AppState.currentChapter;

      html += `<div class="tree-node" data-type="volume" data-id="${vol.id}">`;
      html += `<div class="tree-node-header${volActive ? ' active' : ''}" data-action="select-volume" data-id="${vol.id}">`;
      html += `<span class="toggle${isCollapsed ? '' : ' open'}" data-action="toggle-volume" data-id="${vol.id}">${isCollapsed ? '▶' : '▼'}</span>`;
      html += `<span class="node-title">📁 ${escHtml(vol.title)}</span>`;
      html += `<span class="node-wordcount">${getVolWordCount(vol)} 字</span>`;
      html += `</div>`;

      // 章节列表
      if (!isCollapsed) {
        html += `<div class="tree-node-children">`;
        for (const ch of (vol.chapters || [])) {
          const chActive = AppState.currentChapter?.id === ch.id;
          html += `<div class="tree-node" data-type="chapter" data-id="${ch.id}">`;
          html += `<div class="tree-node-header${chActive ? ' active' : ''}" data-action="select-chapter" data-id="${ch.id}" data-vol="${vol.id}">`;
          html += `<span class="toggle hidden">·</span>`;
          html += `<span class="node-title">${escHtml(ch.title)}</span>`;
          html += `<span class="node-status">${statusLabel(ch.status)}</span>`;
          html += `<span class="node-wordcount">${ch.word_count || 0}</span>`;
          html += `</div></div>`;
        }
        html += `</div>`;
      }

      html += `</div>`;
    }

    container.innerHTML = html;

    // 事件绑定
    container.querySelectorAll('[data-action="toggle-volume"]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const vid = parseInt(el.dataset.id);
        this.collapsedVolumes[vid] = !(this.collapsedVolumes[vid] !== false);
        this.render();
      });
    });

    container.querySelectorAll('[data-action="select-volume"]').forEach(el => {
      el.addEventListener('click', async () => {
        const id = parseInt(el.dataset.id);
        const vol = this.volumeData.find(v => v.id === id);
        AppState.setVolume(vol);
        AppState.setChapter(null);
        Editor.loadVolumePreface(vol);
      });

      el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showContextMenu(e.clientX, e.clientY, 'volume', parseInt(el.dataset.id));
      });
    });

    container.querySelectorAll('[data-action="select-chapter"]').forEach(el => {
      el.addEventListener('click', async () => {
        const chId = parseInt(el.dataset.id);
        const volId = parseInt(el.dataset.vol);
        const vol = this.volumeData.find(v => v.id === volId);
        const ch = vol?.chapters?.find(c => c.id === chId);
        if (vol) AppState.setVolume(vol);
        if (ch) AppState.setChapter(ch);
        Editor.loadChapter(chId);
      });

      el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showContextMenu(e.clientX, e.clientY, 'chapter', parseInt(el.dataset.id));
      });
    });

    // 卷/章拖拽排序与跨卷移动
    this.bindTreeDragDrop(container);
  },

  // 卷/章拖拽（参照剧本目录树的 dragover 指示线模式）：
  // 卷头之间拖放 = 卷排序；章在同卷内拖放 = 章排序；
  // 章拖到另一卷的卷头上或该卷章列表空白处 = 跨卷移动到该卷末尾
  bindTreeDragDrop(container) {
    let dragNode = null; // { type:'volume'|'chapter', id, volId(仅章) }
    const clearIndicators = () => {
      container.querySelectorAll('.tree-node-header').forEach(h => {
        h.style.borderTop = ''; h.style.borderBottom = ''; h.style.outline = '';
        delete h.dataset.dropPos; delete h.dataset.dropVol;
      });
      container.querySelectorAll('.tree-node-children').forEach(c => {
        c.style.outline = ''; delete c.dataset.dropEnd;
      });
    };

    // 卷头可拖拽
    container.querySelectorAll('.tree-node[data-type="volume"] > .tree-node-header').forEach(h => {
      h.draggable = true;
      h.addEventListener('dragstart', (e) => {
        dragNode = { type: 'volume', id: parseInt(h.dataset.id) };
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(dragNode.id));
      });
      h.addEventListener('dragend', () => { dragNode = null; clearIndicators(); });
    });

    // 章可拖拽
    container.querySelectorAll('.tree-node[data-type="chapter"] > .tree-node-header').forEach(h => {
      h.draggable = true;
      h.addEventListener('dragstart', (e) => {
        dragNode = { type: 'chapter', id: parseInt(h.dataset.id), volId: parseInt(h.dataset.vol) };
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(dragNode.id));
      });
      h.addEventListener('dragend', () => { dragNode = null; clearIndicators(); });
    });

    container.addEventListener('dragover', (e) => {
      if (!dragNode || !e.target.closest) return;
      const header = e.target.closest('.tree-node-header');
      // 章拖到某卷章列表的空白处 = 移到该卷末尾
      if (dragNode.type === 'chapter' && !header) {
        const children = e.target.closest('.tree-node-children');
        if (!children) return;
        e.preventDefault();
        clearIndicators();
        children.style.outline = '2px dashed var(--accent)';
        children.dataset.dropEnd = '1';
        return;
      }
      if (!header) return;
      const node = header.closest('.tree-node');
      if (!node) return;
      const targetType = node.dataset.type;
      const targetId = parseInt(header.dataset.id);
      if (dragNode.type === 'volume') {
        // 卷拖到另一卷头上：上/下半区显示插入线
        if (targetType !== 'volume' || targetId === dragNode.id) return;
        e.preventDefault();
        clearIndicators();
        const rect = header.getBoundingClientRect();
        const before = (e.clientY - rect.top) < rect.height / 2;
        header.dataset.dropPos = before ? 'before' : 'after';
        if (before) header.style.borderTop = '2px solid var(--accent)';
        else header.style.borderBottom = '2px solid var(--accent)';
      } else if (targetType === 'chapter') {
        const targetVolId = parseInt(header.dataset.vol);
        if (targetId === dragNode.id) return;
        e.preventDefault();
        clearIndicators();
        if (targetVolId === dragNode.volId) {
          // 同卷内：上/下半区显示插入线
          const rect = header.getBoundingClientRect();
          const before = (e.clientY - rect.top) < rect.height / 2;
          header.dataset.dropPos = before ? 'before' : 'after';
          if (before) header.style.borderTop = '2px solid var(--accent)';
          else header.style.borderBottom = '2px solid var(--accent)';
        } else {
          // 跨卷：高亮目标章，落下即移到该章所在卷末尾
          header.style.outline = '2px solid var(--accent)';
          header.dataset.dropVol = String(targetVolId);
        }
      } else if (targetType === 'volume') {
        // 章拖到另一卷的卷头上 = 移到该卷末尾（高亮卷头）
        if (targetId === dragNode.volId) return;
        e.preventDefault();
        clearIndicators();
        header.style.outline = '2px solid var(--accent)';
        header.dataset.dropVol = String(targetId);
      }
    });

    container.addEventListener('drop', async (e) => {
      if (!dragNode || !e.target.closest) return;
      const info = dragNode;
      const header = e.target.closest('.tree-node-header');
      const children = header ? null : e.target.closest('.tree-node-children');
      // 先取出目标信息再清理状态
      let dropPos = null, dropVol = null, targetId = null, targetType = null;
      if (header) {
        dropPos = header.dataset.dropPos || null;
        dropVol = header.dataset.dropVol ? parseInt(header.dataset.dropVol) : null;
        targetId = parseInt(header.dataset.id);
        targetType = header.closest('.tree-node')?.dataset.type;
      } else if (children?.dataset.dropEnd) {
        const volHeader = children.closest('.tree-node[data-type="volume"]')?.querySelector('.tree-node-header');
        if (volHeader) dropVol = parseInt(volHeader.dataset.id);
      }
      e.preventDefault();
      clearIndicators();
      dragNode = null;
      try {
        if (info.type === 'volume' && targetType === 'volume' && dropPos) {
          // 卷排序：按目标卷上/下方插入
          const ids = this.volumeData.map(v => v.id).filter(id => id !== info.id);
          let at = ids.indexOf(targetId);
          if (at === -1) return;
          if (dropPos === 'after') at += 1;
          ids.splice(at, 0, info.id);
          await api.volume.reorder(AppState.currentProject.id, ids);
        } else if (info.type === 'chapter' && targetType === 'chapter' && dropPos) {
          // 同卷内章排序：按目标章上/下方插入
          const vol = this.volumeData.find(v => v.id === info.volId);
          const ids = (vol?.chapters || []).map(c => c.id).filter(id => id !== info.id);
          let at = ids.indexOf(targetId);
          if (at === -1) return;
          if (dropPos === 'after') at += 1;
          ids.splice(at, 0, info.id);
          await api.chapter.reorder(info.volId, ids);
        } else if (info.type === 'chapter' && dropVol && dropVol !== info.volId) {
          // 跨卷移动到目标卷末尾
          await api.chapter.update(info.id, { volumeId: dropVol });
          toast('已移动到目标卷末尾');
        } else {
          return;
        }
        this.refresh();
      } catch (err) {
        toast('操作失败: ' + err.message, 'error');
      }
    });
  },
};

function getVolWordCount(vol) {
  let total = 0;
  for (const ch of (vol.chapters || [])) total += ch.word_count || 0;
  return total;
}

function statusLabel(s) {
  const map = { draft: '草稿', first_draft: '初稿', revising: '修改中', final: '定稿' };
  return map[s] || s;
}

// ====== 右键菜单 ======
function showContextMenu(x, y, type, id) {
  // 移除旧菜单
  const old = document.querySelector('.context-menu');
  if (old) old.remove();

  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;box-shadow:var(--shadow);z-index:500;min-width:140px;padding:4px;`;
  menu.style.fontSize = '13px';

  const items = [
    type === 'volume' ? null : { label: '重命名', action: () => renameItem(type, id) },
    type === 'volume' ? { label: '重命名', action: () => renameItem(type, id) } : null,
    { label: '删除', action: () => deleteItem(type, id), danger: true },
  ].filter(Boolean);

  menu.innerHTML = items.map(it => `
    <div class="ctx-item" style="padding:6px 12px;border-radius:4px;cursor:pointer;${it.danger?'color:var(--danger)':''}">${it.label}</div>
  `).join('');

  document.body.appendChild(menu);

  menu.querySelectorAll('.ctx-item').forEach((el, i) => {
    el.addEventListener('click', () => { menu.remove(); items[i].action(); });
    el.addEventListener('mouseenter', () => { el.style.background = 'var(--bg-hover)'; });
    el.addEventListener('mouseleave', () => { el.style.background = 'transparent'; });
  });

  const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', close); } };
  setTimeout(() => document.addEventListener('click', close), 0);
}

async function renameItem(type, id) {
  const name = await uiPrompt('新名称:');
  if (!name) return;
  if (type === 'volume') {
    await api.volume.update(id, { title: name });
  } else {
    await api.chapter.update(id, { title: name });
  }
  Sidebar.refresh();
}

async function deleteItem(type, id) {
  if (!await uiConfirm('确定删除吗？将移入回收站。', { danger: true, okText: '删除' })) return;
  if (type === 'volume') {
    await api.volume.delete(id);
  } else {
    await api.chapter.delete(id);
  }
  toast('已移入回收站');
  // 删除的正是当前打开的卷/章时，清空编辑器状态，防止继续写入已删除实体
  if (type === 'volume' && AppState.currentVolume?.id === id) {
    AppState.setVolume(null);
    AppState.setChapter(null);
    Editor.clear();
  } else if (type === 'chapter' && AppState.currentChapter?.id === id) {
    AppState.setChapter(null);
    Editor.clear();
  }
  Sidebar.refresh();
}

// ====== 新建卷/章 ======
async function showAddVolumeModal() {
  const title = await uiPrompt('卷名:');
  if (!title) return;
  await api.volume.create({ projectId: AppState.currentProject.id, title });
  toast('卷已创建', 'success');
  Sidebar.refresh();
}

async function showAddChapterModal() {
  const volId = AppState.currentVolume?.id;
  if (!volId) { toast('请先选择一个卷', 'error'); return; }
  const title = await uiPrompt('章名:');
  if (!title) return;
  await api.chapter.create({ volumeId: volId, projectId: AppState.currentProject.id, title });
  toast('章已创建', 'success');
  Sidebar.refresh();
}

// 迁移期兼容别名:未迁移组件(app.js 等)仍用全局名引用本组件
const Sidebar = NW.plugins.chapter;
window.Sidebar = Sidebar;
