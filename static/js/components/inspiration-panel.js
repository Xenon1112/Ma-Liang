// ====== 灵感面板 ======

const InspirationPanel = {
  selectedType: null,

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;

    const items = await api.inspiration.list(projectId, this.selectedType);
    const types = ['inspiration','reference','quote'];
    const typeLabels = { inspiration:'灵感碎片', reference:'素材参考', quote:'名言引用' };

    const container = document.getElementById('panel-content');
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <strong>灵感</strong>
        <button id="btn-add-inspiration" style="padding:3px 8px;border-radius:4px;background:var(--accent);color:white;font-size:12px;">+ 新增</button>
      </div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;">
        <button class="insp-filter" data-type="" style="padding:2px 6px;border-radius:4px;font-size:11px;${!this.selectedType?'background:var(--accent);color:white;':''}">全部</button>
        ${types.map(t => `
          <button class="insp-filter" data-type="${t}" style="padding:2px 6px;border-radius:4px;font-size:11px;${this.selectedType===t?'background:var(--accent);color:white;':''}">${typeLabels[t]}</button>
        `).join('')}
      </div>
      <div id="insp-list">
        ${items.map(it => `
          <div class="panel-item" data-id="${it.id}" style="display:flex;justify-content:space-between;">
            <div style="flex:1;" data-action="select-insp" data-id="${it.id}">
              <div class="item-title" style="font-size:13px;">${escHtml(it.title)}</div>
              <div class="item-preview">${escHtml((it.content||'').substring(0,50))}</div>
              ${it.tags ? `<div style="font-size:10px;color:var(--accent);">${escHtml(it.tags)}</div>` : ''}
            </div>
            <button class="insp-delete" data-id="${it.id}" style="font-size:10px;color:var(--danger);opacity:0.5;">✕</button>
          </div>
        `).join('') || '<p style="color:var(--text-muted);font-size:12px;">暂无灵感</p>'}
      </div>
      <div id="insp-editor" style="margin-top:12px;"></div>
    `;

    container.querySelectorAll('.insp-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        this.selectedType = btn.dataset.type || null;
        this.refresh();
      });
    });

    container.querySelectorAll('[data-action="select-insp"]').forEach(el => {
      el.addEventListener('click', () => {
        const id = parseInt(el.dataset.id);
        const item = items.find(it => it.id === id);
        if (item) this.showEditor(item);
      });
    });

    container.querySelectorAll('.insp-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm('删除此灵感？')) return;
        await api.inspiration.delete(parseInt(btn.dataset.id));
        this.refresh();
      });
    });

    document.getElementById('btn-add-inspiration').onclick = () => this.showEditor(null);
  },

  showEditor(item) {
    const editorDiv = document.getElementById('insp-editor');
    const isNew = !item;
    editorDiv.innerHTML = `
      <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;padding:12px;">
        <strong>${isNew ? '新增灵感' : '编辑灵感'}</strong>
        <input id="insp-edit-title" placeholder="标题" value="${escAttr(item?.title||'')}" style="width:100%;margin-top:8px;margin-bottom:4px;">
        <select id="insp-edit-type" style="width:100%;margin-bottom:4px;">
          <option value="inspiration" ${item?.type==='inspiration'?'selected':''}>灵感碎片</option>
          <option value="reference" ${item?.type==='reference'?'selected':''}>素材参考</option>
          <option value="quote" ${item?.type==='quote'?'selected':''}>名言引用</option>
        </select>
        <textarea id="insp-edit-content" placeholder="内容..." style="width:100%;height:100px;resize:vertical;margin-bottom:4px;">${escHtml(item?.content||'')}</textarea>
        <input id="insp-edit-source" placeholder="来源（可选）" value="${escAttr(item?.source||'')}" style="width:100%;margin-bottom:4px;">
        <input id="insp-edit-tags" placeholder="标签，逗号分隔（可选）" value="${escAttr(item?.tags||'')}" style="width:100%;margin-bottom:6px;">
        <div style="display:flex;gap:6px;justify-content:flex-end;">
          <button id="insp-cancel" style="padding:4px 12px;border-radius:4px;background:var(--bg-tertiary);">取消</button>
          <button id="insp-save" style="padding:4px 12px;border-radius:4px;background:var(--accent);color:white;">保存</button>
        </div>
      </div>
    `;

    document.getElementById('insp-cancel').onclick = () => { editorDiv.innerHTML = ''; };
    document.getElementById('insp-save').onclick = async () => {
      const title = document.getElementById('insp-edit-title').value.trim();
      if (!title) { toast('请输入标题', 'error'); return; }
      const data = {
        title,
        type: document.getElementById('insp-edit-type').value,
        content: document.getElementById('insp-edit-content').value,
        source: document.getElementById('insp-edit-source').value.trim(),
        tags: document.getElementById('insp-edit-tags').value.trim(),
      };
      if (isNew) {
        data.projectId = AppState.currentProject.id;
        await api.inspiration.create(data);
      } else {
        await api.inspiration.update(item.id, data);
      }
      toast(isNew ? '已保存' : '已更新', 'success');
      editorDiv.innerHTML = '';
      this.refresh();
    };
  },
};
