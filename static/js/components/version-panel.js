// ====== 版本历史面板 ======

const VersionPanel = {
  currentChapterId: null,
  currentVolumeId: null,
  expanded: false,

  async refresh(chapterId, volumeId) {
    this.currentChapterId = chapterId;
    this.currentVolumeId = volumeId;

    const drafts = await api.draft.list(chapterId, volumeId);
    document.getElementById('vp-count').textContent = `${drafts.length} 个版本`;

    const list = document.getElementById('vp-list');
    if (drafts.length === 0) {
      list.innerHTML = '<div style="padding:12px;color:var(--text-muted);text-align:center;">暂无版本记录</div>';
      return;
    }

    list.innerHTML = drafts.map((d, i) => `
      <div class="vp-item${d.is_current ? ' current' : ''}" data-id="${d.id}">
        <div class="vp-info">
          <strong>v${d.version_number}</strong>
          <span>${d.word_count} 字</span>
          <span>${d.created_at?.substring(0,16) || ''}</span>
          <span class="vp-tag">${tagLabel(d.version_tag)}</span>
          ${d.change_note ? `<span style="color:var(--text-muted);font-size:11px;">${escHtml(d.change_note)}</span>` : ''}
        </div>
        <div style="display:flex;gap:4px;">
          <button class="vp-action" data-action="view" data-id="${d.id}" title="查看">👁</button>
          <button class="vp-action" data-action="rollback" data-id="${d.id}" title="回滚" style="color:var(--warning);">↩</button>
          ${i < drafts.length - 1 ? `<button class="vp-action" data-action="diff" data-id="${d.id}" data-prev="${drafts[i+1].id}" title="对比上一版本" style="color:var(--accent);">Δ</button>` : ''}
        </div>
      </div>
    `).join('');

    // 事件
    list.querySelectorAll('[data-action="view"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const draft = await api.draft.get(parseInt(btn.dataset.id));
        showDraftViewModal(draft);
      });
    });

    list.querySelectorAll('[data-action="rollback"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!await uiConfirm('回滚到此版本？当前内容将自动备份为一个新版本。')) return;
        await api.draft.rollback(parseInt(btn.dataset.id));
        toast('已回滚');

        // 重新加载编辑器内容
        if (this.currentChapterId) {
          Editor.loadChapter(this.currentChapterId);
        } else if (this.currentVolumeId) {
          Editor.loadVolumePreface(AppState.currentVolume);
        }
      });
    });

    list.querySelectorAll('[data-action="diff"]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const idA = parseInt(btn.dataset.prev);
        const idB = parseInt(btn.dataset.id);
        const result = await api.draft.diff(idA, idB);
        const draftA = await api.draft.get(idA);
        const draftB = await api.draft.get(idB);
        showDiffModal(draftA, draftB, result);
      });
    });
  },

  toggle() {
    const panel = document.getElementById('version-panel');
    this.expanded = !this.expanded;
    panel.className = this.expanded ? 'expanded' : 'collapsed';
  },
};

function tagLabel(tag) {
  const map = { auto: '自动', manual: '手动', rollback: '回滚', rollback_backup: '回滚备份' };
  return map[tag] || tag;
}

// ====== 查看版本内容 ======
function showDraftViewModal(draft) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" style="min-width:500px;">
      <h3>版本 v${draft.version_number} <span style="font-size:13px;color:var(--text-muted);font-weight:normal;">${draft.created_at?.substring(0,16)} - ${draft.word_count} 字</span></h3>
      <textarea readonly style="width:100%;height:350px;resize:none;font-family:monospace;font-size:14px;padding:12px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);">${escHtml(draft.content)}</textarea>
      <div class="modal-actions">
        <button class="btn-cancel">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
}

// ====== Diff 对比 ======
function showDiffModal(draftA, draftB, diffResult) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'diff-modal';
  overlay.innerHTML = `
    <div class="modal" style="min-width:700px;max-width:900px;">
      <h3>版本对比: v${draftA.version_number} → v${draftB.version_number}</h3>
      <div class="diff-container">
        <div class="diff-column">
          <h4 style="color:var(--danger);">v${draftA.version_number} (旧)</h4>
          <div class="diff-content" id="diff-old"></div>
        </div>
        <div class="diff-column">
          <h4 style="color:var(--success);">v${draftB.version_number} (新)</h4>
          <div class="diff-content" id="diff-new"></div>
        </div>
      </div>
      <div class="diff-summary">
        新增 <span class="added-text">${diffResult.added.length} 行</span> | 删除 <span class="removed-text">${diffResult.removed.length} 行</span>
      </div>
      <div class="modal-actions">
        <button class="btn-cancel">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // 旧版本高亮被删除的行
  const oldLines = (draftA.content || '').split('\n');
  const removedSet = new Set(diffResult.removed.map(r => r.line - 1));
  document.getElementById('diff-old').innerHTML = oldLines.map((line, i) =>
    `<div class="${removedSet.has(i) ? 'diff-removed' : ''}" style="padding:1px 4px;">${escHtml(line) || '&nbsp;'}</div>`
  ).join('');

  // 新版本高亮新增的行
  const newLines = (draftB.content || '').split('\n');
  const addedSet = new Set(diffResult.added.map(r => r.line - 1));
  document.getElementById('diff-new').innerHTML = newLines.map((line, i) =>
    `<div class="${addedSet.has(i) ? 'diff-added' : ''}" style="padding:1px 4px;">${escHtml(line) || '&nbsp;'}</div>`
  ).join('');

  overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
}

// ====== VP Header 点击展开/折叠 ======
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('vp-header').addEventListener('click', () => VersionPanel.toggle());
});
