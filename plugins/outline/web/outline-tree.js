// ====== 大纲面板 ======

NW.plugins.outline = {
  treeData: [],

  async refresh() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;

    this.treeData = await api.outline.tree(projectId);
    this.render();
  },

  render() {
    const container = document.getElementById('panel-content');
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <strong>大纲</strong>
        <div style="display:flex;gap:4px;">
          <button id="btn-collapse-outline" style="padding:3px 6px;border-radius:4px;border:1px solid var(--border-color);font-size:11px;color:var(--text-secondary);" title="全部收起">◀◀</button>
          <button id="btn-add-outline" style="padding:3px 8px;border-radius:4px;background:var(--accent);color:white;font-size:12px;">+ 新增</button>
        </div>
      </div>
      <div id="outline-tree">${this.renderNodes(this.treeData)}</div>
      <div id="outline-editor" style="display:none;margin-top:12px;padding:12px;background:var(--bg-primary);border-radius:6px;border:1px solid var(--border-color);"></div>
    `;

    // 绑定事件
    document.getElementById('btn-add-outline').onclick = () => this.showEditor();

    let allCollapsed = false;
    document.getElementById('btn-collapse-outline').onclick = () => {
      allCollapsed = !allCollapsed;
      container.querySelectorAll('.outline-toggle').forEach(el => {
        const li = el.closest('li');
        const childUl = li?.querySelector('ul');
        if (childUl) {
          childUl.style.display = allCollapsed ? 'none' : '';
          el.textContent = allCollapsed ? '▶' : '▼';
        }
      });
    };

    container.querySelectorAll('.outline-node-title').forEach(el => {
      el.addEventListener('click', () => {
        const id = parseInt(el.dataset.id);
        const node = this.findById(this.treeData, id);
        if (node) this.showEditor(node);
      });
    });

    container.querySelectorAll('.outline-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!await uiConfirm('删除此大纲节点？', { danger: true, okText: '删除' })) return;
        try {
          await api.outline.delete(parseInt(btn.dataset.id));
          this.refresh();
        } catch (err) {
          toast('删除失败: ' + err.message, 'error');
        }
      });
    });

    container.querySelectorAll('.outline-toggle').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const li = el.closest('li');
        const childUl = li.querySelector('ul');
        if (childUl) {
          childUl.style.display = childUl.style.display === 'none' ? '' : 'none';
          el.textContent = childUl.style.display === 'none' ? '▶' : '▼';
        }
      });
    });
  },

  renderNodes(nodes, depth = 0) {
    if (!nodes || nodes.length === 0) return '<p style="color:var(--text-muted);font-size:12px;">暂无大纲，点击"+ 新增"开始</p>';
    let html = '<ul style="padding-left:16px;">';
    for (const node of nodes) {
      html += `<li style="margin-bottom:2px;">`;
      html += `<div style="display:flex;align-items:center;gap:4px;">`;
      html += `<span class="outline-toggle" style="cursor:pointer;font-size:10px;color:var(--text-muted);">${node.children?.length ? '▼' : '·'}</span>`;
      html += `<span class="outline-node-title" data-id="${node.id}" style="cursor:pointer;flex:1;font-size:13px;padding:2px 4px;border-radius:3px;">${escHtml(node.title)} <span style="font-size:10px;color:var(--text-muted);">[${nodeTypeLabel(node.node_type)}]</span></span>`;
      html += `<button class="outline-delete" data-id="${node.id}" style="font-size:10px;padding:0 4px;color:var(--danger);opacity:0.5;">✕</button>`;
      html += `</div>`;
      if (node.children?.length) html += this.renderNodes(node.children, depth + 1);
      html += `</li>`;
    }
    html += '</ul>';
    return html;
  },

  findById(nodes, id) {
    for (const node of nodes) {
      if (node.id === id) return node;
      if (node.children) {
        const found = this.findById(node.children, id);
        if (found) return found;
      }
    }
    return null;
  },

  async showEditor(node) {
    const editorDiv = document.getElementById('outline-editor');
    editorDiv.style.display = 'block';
    const isNew = !node;

    editorDiv.innerHTML = `
      <strong>${isNew ? '新增大纲' : '编辑大纲'}</strong>
      <div style="margin-top:8px;">
        <input id="out-edit-title" placeholder="标题" value="${escAttr(node?.title || '')}" style="width:100%;margin-bottom:6px;">
        <select id="out-edit-type" style="width:100%;margin-bottom:6px;">
          <option value="chapter_outline" ${node?.node_type==='chapter_outline'?'selected':''}>章纲</option>
          <option value="volume_outline" ${node?.node_type==='volume_outline'?'selected':''}>卷纲</option>
          <option value="main_plot" ${node?.node_type==='main_plot'?'selected':''}>主线剧情</option>
          <option value="sub_plot" ${node?.node_type==='sub_plot'?'selected':''}>支线剧情</option>
          <option value="foreshadowing" ${node?.node_type==='foreshadowing'?'selected':''}>伏笔</option>
        </select>
        <textarea id="out-edit-content" placeholder="详细内容..." style="width:100%;height:80px;resize:vertical;margin-bottom:6px;">${escHtml(node?.content || '')}</textarea>
        <div style="display:flex;gap:6px;justify-content:flex-end;">
          <button id="out-cancel" style="padding:4px 12px;border-radius:4px;background:var(--bg-tertiary);">取消</button>
          <button id="out-save" style="padding:4px 12px;border-radius:4px;background:var(--accent);color:white;">保存</button>
        </div>
      </div>
    `;

    document.getElementById('out-cancel').onclick = () => { editorDiv.style.display = 'none'; };
    document.getElementById('out-save').onclick = async () => {
      const title = document.getElementById('out-edit-title').value.trim();
      if (!title) { toast('请输入标题', 'error'); return; }
      const data = {
        projectId: AppState.currentProject.id,
        title,
        nodeType: document.getElementById('out-edit-type').value,
        content: document.getElementById('out-edit-content').value,
        parentId: node?.parent_id || null,
      };
      if (isNew) {
        await api.outline.create(data);
      } else {
        await api.outline.update(node.id, data);
      }
      toast(isNew ? '大纲已创建' : '大纲已更新', 'success');
      editorDiv.style.display = 'none';
      this.refresh();
    };
  },
};

function nodeTypeLabel(type) {
  const map = { main_plot: '主线', sub_plot: '支线', volume_outline: '卷纲', chapter_outline: '章纲', foreshadowing: '伏笔' };
  return map[type] || type;
}

// 迁移期兼容别名:未迁移组件(app.js/search-panel.js)仍用全局名引用本面板
const OutlinePanel = NW.plugins.outline;
window.OutlinePanel = OutlinePanel;
