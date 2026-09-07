// ====== 人物面板 ======

NW.plugins.character = {
  selectedId: null,

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;

    const chars = await api.character.list(projectId);
    const container = document.getElementById('panel-content');

    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <strong>人物</strong>
        <button id="btn-add-character" style="padding:3px 8px;border-radius:4px;background:var(--accent);color:white;font-size:12px;">+ 新增</button>
      </div>
      <div id="char-list">
        ${chars.map(c => `
          <div class="panel-item${this.selectedId === c.id ? ' active' : ''}" data-id="${c.id}" style="display:flex;justify-content:space-between;">
            <span>${escHtml(c.name)}${c.aliases ? ` <span style="color:var(--text-muted);font-size:11px;">(${escHtml(c.aliases)})</span>` : ''}</span>
            <button class="char-delete" data-id="${c.id}" style="font-size:10px;color:var(--danger);opacity:0.5;">✕</button>
          </div>
        `).join('') || '<p style="color:var(--text-muted);font-size:12px;">暂无人物</p>'}
      </div>
      <div id="char-editor" style="margin-top:12px;"></div>
    `;

    document.getElementById('btn-add-character').onclick = () => this.showAddModal();

    container.querySelectorAll('#char-list .panel-item').forEach(item => {
      item.addEventListener('click', (e) => {
        if (e.target.classList.contains('char-delete')) return;
        this.selectChar(parseInt(item.dataset.id));
      });
    });

    container.querySelectorAll('.char-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!await uiConfirm('删除此人物？', { danger: true, okText: '删除' })) return;
        await api.character.delete(parseInt(btn.dataset.id));
        this.selectedId = null;
        this.refresh();
      });
    });

    // 如果之前选中了人物，刷新编辑器；人物已被删除则清除选中
    if (this.selectedId) {
      try {
        const char = await api.character.get(this.selectedId);
        if (char) this.renderEditor(char);
        else this.selectedId = null;
      } catch (err) {
        this.selectedId = null;
      }
    }
  },

  async showAddModal() {
    const name = await uiPrompt('人物姓名:');
    if (!name) return;
    await api.character.create({ projectId: AppState.currentProject.id, name });
    toast('人物已创建', 'success');
    this.refresh();
  },

  async selectChar(id) {
    this.selectedId = id;
    try {
      const char = await api.character.get(id);
      if (!char) throw new Error('not found');
      this.renderEditor(char);
    } catch (err) {
      // 人物可能已被删除：清除选中并刷新列表
      this.selectedId = null;
    }
    this.refresh(); // 更新高亮
  },

  renderEditor(char) {
    const editorDiv = document.getElementById('char-editor');
    editorDiv.innerHTML = `
      <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;padding:12px;">
        <div style="margin-bottom:8px;display:flex;gap:6px;">
          <input id="char-edit-name" value="${escAttr(char.name)}" placeholder="姓名" style="flex:1;">
          <input id="char-edit-aliases" value="${escAttr(char.aliases || '')}" placeholder="别名" style="flex:1;">
        </div>
        <button id="char-save-basic" style="padding:2px 10px;border-radius:4px;background:var(--accent);color:white;font-size:12px;margin-bottom:8px;">保存基本信息</button>
        <hr style="border-color:var(--border-color);margin:8px 0;">
        <div id="char-fields">
          ${(char.fields || []).map(f => `
            <div class="char-field" data-id="${f.id}" style="margin-bottom:8px;border:1px solid var(--border-color);border-radius:4px;overflow:hidden;">
              <div style="display:flex;align-items:center;padding:4px 8px;background:var(--bg-secondary);">
                <input class="char-field-name" value="${escAttr(f.field_name)}" placeholder="字段名" style="flex:1;border:none;background:transparent;font-size:12px;font-weight:bold;">
                <button class="char-field-delete" data-id="${f.id}" style="font-size:10px;color:var(--danger);padding:0 4px;">✕</button>
              </div>
              <textarea class="char-field-content" style="width:100%;border:none;resize:vertical;min-height:40px;padding:6px 8px;font-size:13px;">${escHtml(f.content || '')}</textarea>
            </div>
          `).join('')}
        </div>
        <button id="char-add-field" style="padding:4px 12px;border-radius:4px;border:1px dashed var(--border-color);font-size:12px;color:var(--text-secondary);width:100%;">+ 添加字段</button>

        <div style="margin-top:12px;">
          <strong style="font-size:12px;">出场记录</strong>
          <div id="char-appearances"></div>
        </div>
      </div>
    `;

    // 保存基本信息
    document.getElementById('char-save-basic').onclick = async () => {
      const name = document.getElementById('char-edit-name').value.trim();
      const aliases = document.getElementById('char-edit-aliases').value.trim();
      await api.character.update(char.id, { name, aliases });
      toast('已保存', 'success');
      this.refresh();
    };

    // 保存字段
    editorDiv.querySelectorAll('.char-field').forEach(fieldDiv => {
      const fieldId = parseInt(fieldDiv.dataset.id);
      const nameInput = fieldDiv.querySelector('.char-field-name');
      const contentTextarea = fieldDiv.querySelector('.char-field-content');

      const saveField = debounce(async () => {
        await api.character.updateField(fieldId, {
          fieldName: nameInput.value.trim(),
          content: contentTextarea.value,
        });
      }, 500);

      nameInput.addEventListener('input', saveField);
      contentTextarea.addEventListener('input', saveField);
    });

    // 删除字段（字段内容可能很长，需确认）
    editorDiv.querySelectorAll('.char-field-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!await uiConfirm('删除此字段？字段内容将永久删除。', { danger: true, okText: '删除' })) return;
        const fieldId = parseInt(btn.dataset.id);
        await api.character.removeField(fieldId);
        this.selectChar(char.id); // 刷新编辑器
      });
    });

    // 添加字段
    document.getElementById('char-add-field').onclick = async () => {
      const fieldName = await uiPrompt('字段名（如：外貌、性格、背景）:');
      if (!fieldName) return;
      await api.character.addField({ characterId: char.id, fieldName });
      this.selectChar(char.id);
    };

    // 出场记录
    const appDiv = document.getElementById('char-appearances');
    if (!char.appearances || char.appearances.length === 0) {
      appDiv.innerHTML = '<p style="font-size:11px;color:var(--text-muted);">暂无出场记录</p>';
    } else {
      appDiv.innerHTML = char.appearances.map(a => `
        <div style="font-size:11px;padding:2px 0;color:var(--text-secondary);">
          ${escHtml(a.volume_title)} → ${escHtml(a.chapter_title)} ${a.note ? `(${escHtml(a.note)})` : ''}
        </div>
      `).join('');
    }
  },
};

// 注册右侧栏 tab(消费逻辑见 static/js/core/extensions.js)
NW.registerComponent('sidebar.tabs', {
  id: 'character',
  title: '人物',
  order: 20,
  refresh: () => NW.plugins.character.refresh(),
});

// 迁移期兼容别名:未迁移组件(app.js/search-panel.js 等)仍用全局名引用本面板
const CharacterPanel = NW.plugins.character;
window.CharacterPanel = CharacterPanel;
