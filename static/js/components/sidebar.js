// ====== 目录树 Sidebar ======

const Sidebar = {
  volumeData: [],
  collapsedVolumes: {},

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;

    this.volumeData = await api.volume.list(projectId);

    // 加载每个卷的章节
    for (const vol of this.volumeData) {
      vol.chapters = await api.chapter.list(vol.id);
    }

    this.render();
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
