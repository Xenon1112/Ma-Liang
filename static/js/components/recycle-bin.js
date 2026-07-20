// ====== 回收站 ======

const RecycleBin = {
  async show() {
    const items = await api.recycle.list();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:500px;max-width:650px;">
        <h3>回收站</h3>
        <div style="max-height:400px;overflow-y:auto;margin-bottom:12px;">
          ${items.length === 0 ? '<p style="color:var(--text-muted);text-align:center;padding:20px;">回收站为空</p>' : `
            <table style="width:100%;font-size:13px;border-collapse:collapse;">
              <tr style="border-bottom:1px solid var(--border-color);color:var(--text-secondary);">
                <td style="padding:4px;">类型</td><td style="padding:4px;">名称</td><td style="padding:4px;">剩余天数</td><td style="padding:4px;">操作</td>
              </tr>
              ${items.map(it => `
                <tr style="border-bottom:1px solid var(--border-color);${it.expired?'opacity:0.4':''}">
                  <td style="padding:4px;font-size:11px;">${typeLabel(it.entityType)}</td>
                  <td style="padding:4px;">${escHtml(it.displayName)}</td>
                  <td style="padding:4px;${it.remainingDays<=3?'color:var(--danger);':''}">${it.expired ? '已过期' : it.remainingDays + ' 天'}</td>
                  <td style="padding:4px;display:flex;gap:4px;">
                    <button class="recycle-restore" data-type="${it.entityType}" data-id="${it.entityId}" style="font-size:11px;padding:2px 8px;border-radius:4px;background:var(--accent);color:white;">恢复</button>
                    <button class="recycle-delete" data-type="${it.entityType}" data-id="${it.entityId}" style="font-size:11px;padding:2px 8px;border-radius:4px;background:var(--danger);color:white;">彻底删除</button>
                  </td>
                </tr>
              `).join('')}
            </table>
          `}
        </div>
        <div style="display:flex;justify-content:space-between;">
          <button id="btn-clean-expired" style="padding:6px 12px;border-radius:4px;background:var(--warning);color:white;font-size:12px;">清理过期项</button>
          <button class="btn-cancel">关闭</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    // 恢复
    overlay.querySelectorAll('.recycle-restore').forEach(btn => {
      btn.addEventListener('click', async () => {
        await api.recycle.restore(btn.dataset.type, parseInt(btn.dataset.id));
        toast('已恢复');
        overlay.remove();
        RecycleBin.show();
      });
    });

    // 彻底删除
    overlay.querySelectorAll('.recycle-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('此操作不可撤销，确定彻底删除？')) return;
        await api.recycle.permanentlyDelete(btn.dataset.type, parseInt(btn.dataset.id));
        toast('已彻底删除');
        overlay.remove();
        RecycleBin.show();
      });
    });

    // 清理过期
    document.getElementById('btn-clean-expired').onclick = async () => {
      const count = await api.recycle.cleanExpired();
      toast(`已清理 ${count} 条过期记录`);
      overlay.remove();
      RecycleBin.show();
    };
  },
};

function typeLabel(type) {
  const map = { project:'作品', volume:'卷', chapter:'章', outline:'大纲', character:'人物', world_setting:'设定', inspiration:'灵感' };
  return map[type] || type;
}
