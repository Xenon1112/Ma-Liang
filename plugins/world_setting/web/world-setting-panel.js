// ====== 世界观设定面板 ======

NW.plugins.world_setting = {
  selectedCategory: null,

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;

    const settings = await api.worldSetting.list(projectId, this.selectedCategory);
    const categories = ['geography','history','politics','magic','tech','race','org','other'];
    const catLabels = { geography:'地理', history:'历史', politics:'政治', magic:'魔法体系', tech:'科技水平', race:'种族', org:'组织', other:'其他' };

    const container = document.getElementById('panel-content');
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <strong>世界观设定</strong>
        <button id="btn-add-setting" style="padding:3px 8px;border-radius:4px;background:var(--accent);color:white;font-size:12px;">+ 新增</button>
      </div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;">
        <button class="cat-filter" data-cat="" style="padding:2px 6px;border-radius:4px;font-size:11px;${!this.selectedCategory?'background:var(--accent);color:white;':''}">全部</button>
        ${categories.map(c => `
          <button class="cat-filter" data-cat="${c}" style="padding:2px 6px;border-radius:4px;font-size:11px;${this.selectedCategory===c?'background:var(--accent);color:white;':''}">${catLabels[c]}</button>
        `).join('')}
      </div>
      <div id="setting-list">
        ${settings.map(s => `
          <div class="panel-item" data-id="${s.id}" style="display:flex;justify-content:space-between;">
            <div style="flex:1;" data-action="select-setting" data-id="${s.id}">
              <div class="item-title" style="font-size:13px;">${escHtml(s.title)}</div>
              <div class="item-preview">${escHtml((s.content||'').substring(0,40))}</div>
            </div>
            <button class="setting-delete" data-id="${s.id}" style="font-size:10px;color:var(--danger);opacity:0.5;">✕</button>
          </div>
        `).join('') || '<p style="color:var(--text-muted);font-size:12px;">暂无设定</p>'}
      </div>
      <div id="setting-editor" style="margin-top:12px;"></div>
    `;

    // 分类筛选
    container.querySelectorAll('.cat-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        this.selectedCategory = btn.dataset.cat || null;
        this.refresh();
      });
    });

    // 选中设定
    container.querySelectorAll('[data-action="select-setting"]').forEach(el => {
      el.addEventListener('click', () => {
        const id = parseInt(el.dataset.id);
        const setting = settings.find(s => s.id === id);
        if (setting) this.showEditor(setting);
      });
    });

    // 删除
    container.querySelectorAll('.setting-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!await uiConfirm('删除此设定？', { danger: true, okText: '删除' })) return;
        await api.worldSetting.delete(parseInt(btn.dataset.id));
        this.refresh();
      });
    });

    document.getElementById('btn-add-setting').onclick = () => this.showEditor(null);
  },

  showEditor(setting) {
    const editorDiv = document.getElementById('setting-editor');
    const isNew = !setting;
    editorDiv.innerHTML = `
      <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;padding:12px;">
        <strong>${isNew ? '新增设定' : '编辑设定'}</strong>
        <input id="set-edit-title" placeholder="标题" value="${escAttr(setting?.title||'')}" style="width:100%;margin-top:8px;margin-bottom:4px;">
        <select id="set-edit-cat" style="width:100%;margin-bottom:4px;">
          ${['geography','history','politics','magic','tech','race','org','other'].map(c => `
            <option value="${c}" ${setting?.category===c?'selected':''}>${{geography:'地理',history:'历史',politics:'政治',magic:'魔法体系',tech:'科技水平',race:'种族',org:'组织',other:'其他'}[c]}</option>
          `).join('')}
        </select>
        <textarea id="set-edit-content" placeholder="内容..." style="width:100%;height:120px;resize:vertical;margin-bottom:6px;">${escHtml(setting?.content||'')}</textarea>
        <div style="display:flex;gap:6px;justify-content:flex-end;">
          <button id="set-cancel" style="padding:4px 12px;border-radius:4px;background:var(--bg-tertiary);">取消</button>
          <button id="set-save" style="padding:4px 12px;border-radius:4px;background:var(--accent);color:white;">保存</button>
        </div>
      </div>
    `;

    document.getElementById('set-cancel').onclick = () => { editorDiv.innerHTML = ''; };
    document.getElementById('set-save').onclick = async () => {
      const title = document.getElementById('set-edit-title').value.trim();
      if (!title) { toast('请输入标题', 'error'); return; }
      const data = {
        title,
        category: document.getElementById('set-edit-cat').value,
        content: document.getElementById('set-edit-content').value,
      };
      if (isNew) {
        data.projectId = AppState.currentProject.id;
        await api.worldSetting.create(data);
      } else {
        await api.worldSetting.update(setting.id, data);
      }
      toast(isNew ? '设定已创建' : '设定已更新', 'success');
      editorDiv.innerHTML = '';
      this.refresh();
    };
  },
};

// 迁移期兼容别名:未迁移组件(app.js/search-panel.js)仍用全局名引用本面板
const WorldSettingPanel = NW.plugins.world_setting;
window.WorldSettingPanel = WorldSettingPanel;
