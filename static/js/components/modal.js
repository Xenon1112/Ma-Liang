// ====== 通用模态对话框（替代原生 prompt/confirm，避免焦点吞字与阻塞问题）======

/**
 * 输入对话框，等价于 prompt()，但为页面内模态框。
 * @param {string} title 标题
 * @param {object} opts { placeholder, defaultValue }
 * @returns {Promise<string|null>} 用户输入（取消返回 null）
 */
function uiPrompt(title, opts = {}) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:360px;">
        <h3>${escHtml(title)}</h3>
        <div class="form-group" style="margin-top:12px;">
          <input id="ui-prompt-input" type="text" placeholder="${escAttr(opts.placeholder || '')}" value="${escAttr(opts.defaultValue || '')}" style="width:100%;">
        </div>
        <div class="modal-actions" style="margin-top:16px;">
          <button class="btn-cancel">取消</button>
          <button class="btn-primary">确定</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const input = overlay.querySelector('#ui-prompt-input');
    // 延迟聚焦，确保弹窗渲染完成后焦点稳定
    setTimeout(() => { input.focus(); input.select(); }, 50);

    const done = (val) => { overlay.remove(); resolve(val); };
    overlay.querySelector('.btn-cancel').onclick = () => done(null);
    overlay.querySelector('.btn-primary').onclick = () => {
      const v = input.value.trim();
      if (!v) { input.focus(); return; }
      done(v);
    };
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); overlay.querySelector('.btn-primary').click(); }
      if (e.key === 'Escape') done(null);
    });
    overlay.addEventListener('click', (e) => { if (e.target === overlay) done(null); });
  });
}

/**
 * 勾选列表弹窗（多选）。
 * @param {string} title 标题
 * @param {Array<{id:*, label:string}>} options 可选项
 * @param {Array<*>} selectedIds 已选中的 id
 * @returns {Promise<Array|null>} 选中的 id 数组（取消返回 null）
 */
function uiChecklist(title, options, selectedIds = []) {
  return new Promise((resolve) => {
    const selected = new Set(selectedIds);
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:320px;max-width:420px;">
        <h3>${escHtml(title)}</h3>
        <div style="max-height:300px;overflow-y:auto;margin:12px 0;display:flex;flex-direction:column;gap:4px;">
          ${options.map(o => `
            <label style="display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--border-color);border-radius:6px;cursor:pointer;">
              <input type="checkbox" value="${escAttr(String(o.id))}" ${selected.has(o.id) ? 'checked' : ''}>
              <span>${escHtml(o.label)}</span>
            </label>
          `).join('') || '<p style="color:var(--text-muted);font-size:13px;">无可选项</p>'}
        </div>
        <div class="modal-actions">
          <button class="btn-cancel">取消</button>
          <button class="btn-primary">确定</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const done = (val) => { overlay.remove(); resolve(val); };
    overlay.querySelector('.btn-cancel').onclick = () => done(null);
    overlay.querySelector('.btn-primary').onclick = () => {
      const ids = [...overlay.querySelectorAll('input[type=checkbox]:checked')].map(cb => {
        const v = cb.value;
        const n = Number(v);
        return isNaN(n) ? v : n;
      });
      done(ids);
    };
    overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') done(null); });
    overlay.addEventListener('click', (e) => { if (e.target === overlay) done(null); });
  });
}

/**
 * 确认对话框，等价于 confirm()。
 * @param {string} message 提示信息
 * @param {object} opts { danger, okText }
 * @returns {Promise<boolean>}
 */
function uiConfirm(message, opts = {}) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:360px;">
        <h3>确认操作</h3>
        <p style="margin:12px 0;line-height:1.6;">${escHtml(message)}</p>
        <div class="modal-actions">
          <button class="btn-cancel">取消</button>
          <button class="btn-primary" ${opts.danger ? 'style="background:var(--danger);border-color:var(--danger);"' : ''}>${escHtml(opts.okText || '确定')}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const done = (val) => { overlay.remove(); resolve(val); };
    overlay.querySelector('.btn-cancel').onclick = () => done(false);
    overlay.querySelector('.btn-primary').onclick = () => done(true);
    overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') done(false); });
    overlay.addEventListener('click', (e) => { if (e.target === overlay) done(false); });
    setTimeout(() => overlay.querySelector('.btn-primary').focus(), 50);
  });
}
