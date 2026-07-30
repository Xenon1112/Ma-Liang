// ====== 作品列表页 ======

const ProjectList = {
  async refresh() {
    const projects = await api.project.list();
    const grid = document.getElementById('project-grid');
    if (projects.length === 0) {
      grid.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">还没有作品，点击上方按钮新建</p>';
      return;
    }
    grid.innerHTML = projects.map(p => {
      const typeLabel = typeBadge(p.project_type);
      // 统计行按作品类型区分：小说为「章 · 字」，剧本为「幕 · 场 · 字」（音乐剧另附歌曲数）
      const isScript = p.project_type === 'play' || p.project_type === 'musical';
      const statsHtml = isScript
        ? `<span>${p.actCount || 0} 幕</span>
            <span>${p.sceneCount || 0} 场</span>
            <span>${p.totalWords || 0} 字</span>` +
          (p.project_type === 'musical' ? `<span>${p.songCount || 0} 歌</span>` : '')
        : `<span>${p.chapterCount || 0} 章</span>
            <span>${p.totalWords || 0} 字</span>`;
      return `
        <div class="project-card" data-id="${p.id}">
          <h3>${escHtml(p.title)} ${typeLabel}</h3>
          <div class="card-desc">${escHtml(p.description || '暂无简介')}</div>
          <div class="card-stats">
            ${statsHtml}
            <span>${p.status === 'writing' ? '写作中' : p.status === 'completed' ? '已完成' : '暂停'}</span>
            <span>${p.updated_at?.substring(0,10) || ''}</span>
          </div>
          <div class="card-actions">
            <button class="btn-edit" data-action="edit" data-id="${p.id}">编辑</button>
            <button class="btn-delete" data-action="delete" data-id="${p.id}">删除</button>
          </div>
        </div>`;
    }).join('');

    // 点击卡片打开作品（点击操作按钮除外）
    grid.querySelectorAll('.project-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.dataset.action) return;
        App.openProject(parseInt(card.dataset.id));
      });
    });

    // 编辑按钮：修改作品基本信息
    grid.querySelectorAll('.btn-edit').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const p = projects.find(x => x.id === parseInt(btn.dataset.id));
        if (p) showEditProjectModal(p);
      });
    });

    // 删除按钮
    grid.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        if (await uiConfirm('确定删除这个作品吗？将移入回收站，30天后自动清除。', { danger: true, okText: '删除' })) {
          await api.project.delete(id);
          toast('作品已移入回收站');
          ProjectList.refresh();
        }
      });
    });
  },
};

// ====== 新建作品弹窗 ======

function showNewProjectModal() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h3>新建作品</h3>
      <div class="form-group">
        <label>作品标题 *</label>
        <input id="new-project-title" type="text" placeholder="输入作品标题">
      </div>
      <div class="form-group">
        <label>类型</label>
        <select id="new-project-type">
          <option value="novel">小说</option>
          <option value="play">话剧剧本</option>
          <option value="musical">音乐剧剧本</option>
        </select>
      </div>
      <div class="form-group">
        <label>简介</label>
        <textarea id="new-project-desc" placeholder="写一句简介..."></textarea>
      </div>
      <div class="form-group">
        <label>笔名</label>
        <input id="new-project-author" type="text" placeholder="你的笔名">
      </div>
      <div class="modal-actions">
        <button class="btn-cancel">取消</button>
        <button class="btn-primary" id="btn-create-project">创建</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
  overlay.querySelector('#btn-create-project').onclick = async () => {
    const title = document.getElementById('new-project-title').value.trim();
    if (!title) { toast('请输入作品标题', 'error'); return; }
    const desc = document.getElementById('new-project-desc').value.trim();
    const author = document.getElementById('new-project-author').value.trim();
    const projectType = document.getElementById('new-project-type').value;
    await api.project.create({ title, description: desc, author, projectType });
    overlay.remove();
    toast('作品创建成功', 'success');
    ProjectList.refresh();
  };

  // 点击遮罩关闭
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  // Enter 提交
  overlay.querySelector('#new-project-title').focus();
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') overlay.remove();
  });
}

// ====== 编辑作品弹窗（标题/副标题/笔名/简介/状态）======

function showEditProjectModal(p) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h3>编辑作品信息</h3>
      <div class="form-group">
        <label>作品标题 *</label>
        <input id="edit-project-title" type="text" value="${escAttr(p.title)}" placeholder="输入作品标题">
      </div>
      <div class="form-group">
        <label>副标题</label>
        <input id="edit-project-subtitle" type="text" value="${escAttr(p.subtitle || '')}" placeholder="副标题（可选）">
      </div>
      <div class="form-group">
        <label>笔名</label>
        <input id="edit-project-author" type="text" value="${escAttr(p.author || '')}" placeholder="你的笔名">
      </div>
      <div class="form-group">
        <label>简介</label>
        <textarea id="edit-project-desc" placeholder="写一句简介...">${escHtml(p.description || '')}</textarea>
      </div>
      <div class="form-group">
        <label>状态</label>
        <select id="edit-project-status">
          <option value="writing" ${p.status === 'writing' ? 'selected' : ''}>写作中</option>
          <option value="completed" ${p.status === 'completed' ? 'selected' : ''}>已完成</option>
          <option value="paused" ${p.status === 'paused' ? 'selected' : ''}>暂停</option>
        </select>
      </div>
      <div class="modal-actions">
        <button class="btn-cancel">取消</button>
        <button class="btn-primary" id="btn-save-project">保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
  overlay.querySelector('#btn-save-project').onclick = async () => {
    const title = document.getElementById('edit-project-title').value.trim();
    if (!title) { toast('请输入作品标题', 'error'); return; }
    await api.project.update(p.id, {
      title,
      subtitle: document.getElementById('edit-project-subtitle').value.trim(),
      author: document.getElementById('edit-project-author').value.trim(),
      description: document.getElementById('edit-project-desc').value.trim(),
      status: document.getElementById('edit-project-status').value,
    });
    overlay.remove();
    toast('已保存', 'success');
    ProjectList.refresh();
  };

  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') overlay.remove(); });
  overlay.querySelector('#edit-project-title').focus();
}

function typeBadge(type) {
  const map = {
    novel: '<span class="badge badge-novel">小说</span>',
    play: '<span class="badge badge-play">话剧</span>',
    musical: '<span class="badge badge-musical">音乐剧</span>',
  };
  return map[type] || '';
}

// ====== 导入作品（JSON）======

// 在作品列表工具区插入「导入」按钮，配合隐藏的文件选择框读取 JSON 导出文件
function initImportProjectButton() {
  const newBtn = document.getElementById('btn-new-project');
  if (!newBtn || document.getElementById('btn-import-project')) return;

  const btn = document.createElement('button');
  btn.className = 'btn-new-project';
  btn.id = 'btn-import-project';
  btn.textContent = '导入';
  newBtn.insertAdjacentElement('afterend', btn);

  const input = document.createElement('input');
  input.type = 'file';
  input.id = 'import-project-file';
  input.accept = '.json,application/json';
  input.style.display = 'none';
  document.body.appendChild(input);

  btn.addEventListener('click', () => {
    input.value = ''; // 允许重复选择同一个文件
    input.click();
  });

  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    let data;
    try {
      const text = await readFileAsText(file);
      data = JSON.parse(text);
    } catch (err) {
      toast('导入失败: 文件不是合法的 JSON', 'error');
      return;
    }
    try {
      const result = await api.project.importProject(data);
      toast(`已导入副本：${result.project.title}`, 'success');
      ProjectList.refresh();
    } catch (err) {
      toast('导入失败: ' + err.message, 'error');
    }
  });
}

// FileReader 读取文本（Promise 封装）
function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file, 'UTF-8');
  });
}

// 脚本在 body 末尾加载，DOM 已就绪；保险起见做一次状态判断
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initImportProjectButton);
} else {
  initImportProjectButton();
}
