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
      const stats = `卷 ? 章 · ? 字`;
      return `
        <div class="project-card" data-id="${p.id}">
          <h3>${escHtml(p.title)}</h3>
          <div class="card-desc">${escHtml(p.description || '暂无简介')}</div>
          <div class="card-stats">
            <span>${p.status === 'writing' ? '写作中' : p.status === 'completed' ? '已完成' : '暂停'}</span>
            <span>${p.updated_at?.substring(0,10) || ''}</span>
          </div>
          <div class="card-actions">
            <button class="btn-delete" data-action="delete" data-id="${p.id}">删除</button>
          </div>
        </div>`;
    }).join('');

    // 点击卡片打开作品
    grid.querySelectorAll('.project-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.dataset.action === 'delete') return;
        App.openProject(parseInt(card.dataset.id));
      });
    });

    // 删除按钮
    grid.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        if (confirm('确定删除这个作品吗？将移入回收站，30天后自动清除。')) {
          await api.project.delete(id);
          toast('作品已移入回收站');
          ProjectList.refresh();
        }
      });
    });

    // 加载每个作品的统计
    for (const p of projects) {
      const stats = await api.project.getStats(p.id);
      const card = grid.querySelector(`.project-card[data-id="${p.id}"]`);
      if (card) {
        card.querySelector('.card-stats').innerHTML = `
          <span>${stats.chapterCount} 章</span>
          <span>${stats.totalWords} 字</span>
          <span>${p.status === 'writing' ? '写作中' : p.status === 'completed' ? '已完成' : '暂停'}</span>
          <span>${p.updated_at?.substring(0,10) || ''}</span>
        `;
      }
    }
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
    await api.project.create({ title, description: desc, author });
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
