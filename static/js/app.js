// ====== 应用入口 ======

// 全局工具函数
function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escAttr(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; }, 2000);
  setTimeout(() => el.remove(), 2500);
}

// ====== 主题按钮指示（显示当前主题名）======
function updateThemeButton() {
  const label = { light: '亮色', dark: '暗色', warm: '护眼' }[AppState.theme] || AppState.theme;
  const btn = document.getElementById('btn-theme');
  if (btn) btn.textContent = `主题·${label}`;
}

// ====== App 核心逻辑 ======
const App = {
  async init() {
    // 加载配置
    try {
      const config = await api.app.getConfig();
      AppState.config = config;
      AppState.setTheme(config.theme || 'light');
      updateThemeButton();
    } catch (e) {
      console.log('Config not loaded, using defaults');
    }

    // 加载自定义快捷键绑定
    Shortcuts.load();

    // 显示版本号
    try {
      const ver = await api._get('/api/version');
      const label = `${ver.name} v${ver.version}${ver.channel ? ' ' + ver.channel : ''}`;
      document.getElementById('toolbar-title').textContent = label;
      document.title = label;
    } catch (e) { /* 忽略 */ }

    // 显示作品列表（失败时也要继续绑定后续按钮，否则全页面按钮无响应）
    try {
      await ProjectList.refresh();
    } catch (e) {
      toast('加载作品列表失败: ' + (e.message || e), 'error');
    }

    // 绑定工具栏按钮
    document.getElementById('btn-new-project').addEventListener('click', showNewProjectModal);

    document.getElementById('btn-back').addEventListener('click', () => {
      App.closeProject();
    });

    document.getElementById('btn-search').addEventListener('click', () => {
      SearchPanel.show();
    });

    document.getElementById('btn-focus').addEventListener('click', () => {
      App.toggleFocus();
    });

    document.getElementById('btn-theme').addEventListener('click', () => {
      App.cycleTheme();
    });

    document.getElementById('btn-export').addEventListener('click', () => {
      ExportDialog.show();
    });

    document.getElementById('btn-backup').addEventListener('click', async () => {
      await BackupDialog.show();
    });

    document.getElementById('btn-recycle').addEventListener('click', () => {
      RecycleBin.show();
    });

    document.getElementById('btn-shortcuts').addEventListener('click', () => {
      Shortcuts.openSettings();
    });

    // 手动保存：小说冲刷自动保存并立即存草稿；剧本保存当前场景所有卡片
    document.getElementById('btn-save').addEventListener('click', async () => {
      if (!AppState.currentProject) { toast('请先打开一个作品'); return; }
      const isScript = AppState.currentProject.project_type && AppState.currentProject.project_type !== 'novel';
      if (isScript) {
        if (await CardEditor.saveAll()) toast('已保存');
        else toast('请先选择左侧的场景');
      } else {
        if (await Editor.save()) toast('已保存');
      }
    });

    // 侧边栏收起/展开（状态存 localStorage，下次启动恢复）
    const setSidebarCollapsed = (collapsed) => {
      document.getElementById('sidebar').classList.toggle('collapsed', collapsed);
      document.getElementById('btn-expand-sidebar').style.display = collapsed ? '' : 'none';
      localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
    };
    document.getElementById('btn-collapse-sidebar').addEventListener('click', () => setSidebarCollapsed(true));
    document.getElementById('btn-expand-sidebar').addEventListener('click', () => setSidebarCollapsed(false));
    if (localStorage.getItem('sidebarCollapsed') === '1') setSidebarCollapsed(true);

    // 优雅退出：确认后通知后端关闭服务，并替换为退出提示页
    document.getElementById('btn-quit').addEventListener('click', async () => {
      if (!await uiConfirm('确定退出马良吗？写作内容已自动保存。', { okText: '退出' })) return;
      try { await api._post('/api/shutdown'); } catch (e) { /* 服务器可能已开始关闭 */ }
      document.body.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;gap:12px;color:var(--text-secondary);">
        <div style="font-size:20px;">已安全退出马良</div>
        <div style="font-size:14px;">可以关闭此窗口了</div>
      </div>`;
    });

    // 卷/章/幕/场 操作按钮（根据项目类型分发）
    document.getElementById('btn-add-volume').addEventListener('click', () => {
      if (AppState.currentProject?.project_type && AppState.currentProject.project_type !== 'novel') {
        showAddActModal();
      } else {
        showAddVolumeModal();
      }
    });
    document.getElementById('btn-add-chapter').addEventListener('click', () => {
      if (AppState.currentProject?.project_type && AppState.currentProject.project_type !== 'novel') {
        showAddSceneModal();
      } else {
        showAddChapterModal();
      }
    });
    document.getElementById('btn-outline').addEventListener('click', () => {
      toggleRightPanel();
      AppState.rightPanelTab = 'outline';
      switchRightTab('outline');
      OutlinePanel.refresh();
    });

    // 右侧面板收起/展开（状态存 localStorage，下次启动恢复）
    document.getElementById('btn-collapse-right').addEventListener('click', () => setRightPanelCollapsed(true));
    document.getElementById('btn-expand-right').addEventListener('click', () => {
      setRightPanelCollapsed(false);
      switchRightTab(AppState.rightPanelTab || 'outline');
    });
    if (localStorage.getItem('rightPanelCollapsed') === '1') setRightPanelCollapsed(true);

    // 右侧面板标签切换
    document.querySelectorAll('.panel-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        AppState.rightPanelTab = tabName;
        switchRightTab(tabName);
      });
    });

    // 页面关闭/刷新前兜底保存（自动保存是防抖的，直接关窗可能丢最后几秒内容）
    window.addEventListener('pagehide', () => {
      Editor.saveOnUnload();
      if (typeof CardEditor !== 'undefined') CardEditor.saveAllOnUnload();
    });

    // 键盘快捷键（可自定义，见 Shortcuts）
    document.addEventListener('keydown', (e) => {
      const act = Shortcuts.actionFor(e);
      if (act === 'global.search') {
        e.preventDefault();
        SearchPanel.show();
        return;
      }
      if (act === 'global.focus') {
        e.preventDefault();
        App.toggleFocus();
        return;
      }
      if (act === 'global.prevChapter') {
        e.preventDefault();
        App.navigateChapter(-1);
        return;
      }
      if (act === 'global.nextChapter') {
        e.preventDefault();
        App.navigateChapter(1);
        return;
      }
      // Esc 关闭搜索 / 退出专注模式（固定键）
      if (e.key === 'Escape') {
        if (SearchPanel.visible) {
          SearchPanel.hide();
        } else if (AppState.isFocusMode) {
          App.toggleFocus();
        }
      }
    });
  },

  async openProject(id) {
    let project;
    try {
      project = await api.project.get(id);
    } catch (e) {
      toast('打开作品失败: ' + (e.message || e), 'error');
      return;
    }
    if (!project) return;

    AppState.setProject(project);
    AppState.currentAct = null;
    AppState.currentScene = null;
    AppState.setView('workspace');

    document.getElementById('project-list-page').style.display = 'none';
    document.getElementById('workspace').classList.remove('hidden');
    document.getElementById('btn-back').style.display = '';
    document.getElementById('toolbar-title').textContent = project.title;
    document.getElementById('sidebar-actions').style.display = '';

    const isScript = project.project_type === 'play' || project.project_type === 'musical';
    // 切换编辑器视图
    document.getElementById('editor').style.display = isScript ? 'none' : '';
    const cardWrap = document.getElementById('card-editor-wrap');
    if (cardWrap) cardWrap.style.display = isScript ? '' : 'none';

    if (isScript) {
      document.getElementById('btn-add-volume').textContent = '🎭+';
      document.getElementById('btn-add-volume').title = '新建幕';
      document.getElementById('btn-add-chapter').textContent = '🎬+';
      document.getElementById('btn-add-chapter').title = '新建场';
      await ScriptSidebar.refresh();
      CardEditor.clear();
      FloatingSongEditor.clear();
    } else {
      document.getElementById('btn-add-volume').textContent = '📁+';
      document.getElementById('btn-add-volume').title = '新建卷';
      document.getElementById('btn-add-chapter').textContent = '📄+';
      document.getElementById('btn-add-chapter').title = '新建章';
      await Sidebar.refresh();
      Editor.clear();
    }
  },

  closeProject() {
    if (AppState.isDirty) {
      Editor.save();
    }
    AppState.setProject(null);
    AppState.setVolume(null);
    AppState.setChapter(null);
    AppState.setView('project-list');

    document.getElementById('project-list-page').style.display = '';
    document.getElementById('workspace').classList.add('hidden');
    document.getElementById('btn-back').style.display = 'none';
    document.getElementById('toolbar-title').textContent = '马良';
    document.getElementById('sidebar-actions').style.display = 'none';

    ProjectList.refresh();
  },

  toggleFocus() {
    AppState.setFocusMode(!AppState.isFocusMode);
    document.body.classList.toggle('focus-mode', AppState.isFocusMode);
    toast(AppState.isFocusMode ? '专注模式 (Esc 退出)' : '退出专注模式');
  },

  cycleTheme() {
    const themes = ['light', 'dark', 'warm'];
    const idx = themes.indexOf(AppState.theme);
    const next = themes[(idx + 1) % themes.length];
    AppState.setTheme(next);
    api.app.setConfig({ theme: next });
    updateThemeButton();
    toast(`已切换为${next === 'light' ? '亮色' : next === 'dark' ? '暗色' : '护眼'}主题`);
  },

  async navigateChapter(direction) {
    // 剧本/音乐剧项目：按"场"导航（跨幕时进入相邻幕的末场/首场）
    const ptype = AppState.currentProject?.project_type;
    if (ptype && ptype !== 'novel') {
      const flat = [];
      for (const act of (ScriptSidebar.actData || [])) {
        for (const sc of (act.scenes || [])) flat.push({ act, sc });
      }
      const curIdx = flat.findIndex(x => x.sc.id === AppState.currentScene?.id);
      const next = flat[curIdx + direction];
      if (!next) return;
      AppState.currentAct = next.act;
      AppState.currentScene = next.sc;
      await CardEditor.loadScene(next.sc.id);
      ScriptSidebar.render();
      return;
    }
    const volId = AppState.currentVolume?.id;
    if (!volId) return;
    const chapters = await api.chapter.list(volId);
    const currentIdx = chapters.findIndex(c => c.id === AppState.currentChapter?.id);
    const newIdx = currentIdx + direction;
    if (newIdx >= 0 && newIdx < chapters.length) {
      const ch = chapters[newIdx];
      AppState.setChapter(ch);
      Editor.loadChapter(ch.id);
      // 更新树的高亮
      Sidebar.render();
    }
  },
};

// ====== 右侧面板操作 ======
function setRightPanelCollapsed(collapsed) {
  document.getElementById('right-panel').classList.toggle('collapsed', collapsed);
  document.getElementById('right-expand-strip').style.display = collapsed ? '' : 'none';
  localStorage.setItem('rightPanelCollapsed', collapsed ? '1' : '0');
}

function toggleRightPanel() {
  const collapsed = !document.getElementById('right-panel').classList.contains('collapsed');
  setRightPanelCollapsed(collapsed);
}

function switchRightTab(tabName) {
  // 展开面板
  setRightPanelCollapsed(false);

  // 更新标签高亮
  document.querySelectorAll('.panel-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabName);
  });

  // 刷新对应内容
  AppState.rightPanelTab = tabName;
  if (tabName === 'outline') OutlinePanel.refresh();
  else if (tabName === 'character') CharacterPanel.refresh();
  else if (tabName === 'world') WorldSettingPanel.refresh();
  else if (tabName === 'inspiration') InspirationPanel.refresh();
}

// ====== 备份对话框 ======
const BackupDialog = {
  async show() {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:400px;">
        <h3>备份与恢复</h3>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:16px;">
          <button class="btn-primary" id="btn-do-backup" style="padding:10px;">📦 创建备份（保存到用户目录）</button>
          <div>
            <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:4px;">从备份恢复（需要重启应用）</label>
            <select id="restore-select" style="width:100%;margin-bottom:4px;"></select>
            <input id="restore-path" type="text" placeholder="或输入其他备份文件的完整路径" style="width:100%;padding:8px;margin-bottom:4px;">
            <button id="btn-do-restore" style="padding:6px 12px;border:1px solid var(--danger);border-radius:4px;color:var(--danger);">📂 从备份恢复</button>
          </div>
          <button id="btn-show-db-path" style="padding:10px;border:1px solid var(--border-color);border-radius:6px;">📁 查看数据库文件位置</button>
        </div>
        <div class="modal-actions" style="margin-top:16px;">
          <button class="btn-cancel">关闭</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    // 加载备份文件列表（用户目录下本应用创建的备份）
    const select = overlay.querySelector('#restore-select');
    try {
      const backups = await api.backup.list();
      if (backups.length === 0) {
        select.innerHTML = '<option value="">（暂无备份文件）</option>';
      } else {
        select.innerHTML = backups.map(b => {
          const sizeMB = (b.fileSize / 1024 / 1024).toFixed(1);
          const date = (b.date || '').replace('T', ' ').substring(0, 19);
          return `<option value="${escAttr(b.filePath)}">${escHtml(date)}（${sizeMB} MB）</option>`;
        }).join('');
      }
    } catch (e) {
      select.innerHTML = '<option value="">（备份列表加载失败）</option>';
    }

    overlay.querySelector('#btn-do-backup').onclick = async () => {
      try {
        const result = await api.backup.create();
        toast(`备份已保存: ${result.filePath}`, 'success');
        overlay.remove();
      } catch (err) {
        toast('备份失败: ' + err.message, 'error');
      }
    };

    overlay.querySelector('#btn-do-restore').onclick = async () => {
      // 优先使用手动输入的路径，否则用下拉选中的备份
      const filePath = document.getElementById('restore-path').value.trim() || select.value;
      if (!filePath) { toast('请选择或输入备份文件路径', 'error'); return; }
      if (!await uiConfirm('恢复备份将覆盖当前所有数据并重启应用，确定继续？', { danger: true, okText: '恢复' })) return;
      try {
        await api.backup.restore(filePath);
        toast('备份已恢复，请手动重启应用', 'info');
        overlay.remove();
      } catch (err) {
        toast('恢复失败: ' + err.message, 'error');
      }
    };

    overlay.querySelector('#btn-show-db-path').onclick = async () => {
      const result = await api.backup.getDbPath();
      toast(`数据库位置: ${result.dbPath}`, 'info');
    };
  },
};

// ====== 初始化 ======
document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
