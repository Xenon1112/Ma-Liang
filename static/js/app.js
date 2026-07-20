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

// ====== App 核心逻辑 ======
const App = {
  async init() {
    // 加载配置
    try {
      const config = await api.app.getConfig();
      AppState.config = config;
      AppState.setTheme(config.theme || 'light');
    } catch (e) {
      console.log('Config not loaded, using defaults');
    }

    // 显示作品列表
    await ProjectList.refresh();

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

    // 卷/章 操作按钮
    document.getElementById('btn-add-volume').addEventListener('click', showAddVolumeModal);
    document.getElementById('btn-add-chapter').addEventListener('click', showAddChapterModal);
    document.getElementById('btn-outline').addEventListener('click', () => {
      toggleRightPanel();
      AppState.rightPanelTab = 'outline';
      switchRightTab('outline');
      OutlinePanel.refresh();
    });

    // 右侧面板标签切换
    document.querySelectorAll('.panel-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        AppState.rightPanelTab = tabName;
        switchRightTab(tabName);
      });
    });

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
      // Ctrl+P 搜索
      if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        SearchPanel.show();
      }
      // F11 专注模式
      if (e.key === 'F11') {
        e.preventDefault();
        App.toggleFocus();
      }
      // Esc 关闭搜索 / 退出专注模式
      if (e.key === 'Escape') {
        if (SearchPanel.visible) {
          SearchPanel.hide();
        } else if (AppState.isFocusMode) {
          App.toggleFocus();
        }
      }
      // Ctrl+↑ Ctrl+↓ 切换章节
      if ((e.ctrlKey || e.metaKey) && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
        e.preventDefault();
        App.navigateChapter(e.key === 'ArrowUp' ? -1 : 1);
      }
    });
  },

  async openProject(id) {
    const project = await api.project.get(id);
    if (!project) return;

    AppState.setProject(project);
    AppState.setView('workspace');

    document.getElementById('project-list-page').style.display = 'none';
    document.getElementById('workspace').classList.remove('hidden');
    document.getElementById('btn-back').style.display = '';
    document.getElementById('toolbar-title').textContent = project.title;
    document.getElementById('sidebar-actions').style.display = '';

    await Sidebar.refresh();
    Editor.clear();
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
    document.getElementById('toolbar-title').textContent = '小说写作助手';
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
    toast(`已切换为${next === 'light' ? '亮色' : next === 'dark' ? '暗色' : '护眼'}主题`);
  },

  async navigateChapter(direction) {
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
function toggleRightPanel() {
  const panel = document.getElementById('right-panel');
  panel.classList.toggle('collapsed');
}

function switchRightTab(tabName) {
  // 展开面板
  const panel = document.getElementById('right-panel');
  panel.classList.remove('collapsed');

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
            <input id="restore-path" type="text" placeholder="输入备份文件完整路径来恢复" style="width:100%;padding:8px;margin-bottom:4px;">
            <button id="btn-do-restore" style="padding:6px 12px;border:1px solid var(--danger);border-radius:4px;color:var(--danger);">📂 从备份恢复（需要重启应用）</button>
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

    overlay.querySelector('#btn-do-backup').onclick = async () => {
      const result = await api.backup.create();
      toast(`备份已保存: ${result.filePath}`, 'success');
      overlay.remove();
    };

    overlay.querySelector('#btn-do-restore').onclick = async () => {
      const filePath = document.getElementById('restore-path').value.trim();
      if (!filePath) { toast('请输入备份文件路径', 'error'); return; }
      if (!confirm('恢复备份将覆盖当前所有数据并重启应用，确定继续？')) return;
      await api.backup.restore(filePath);
      toast('备份已恢复，请手动重启应用', 'info');
      overlay.remove();
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
