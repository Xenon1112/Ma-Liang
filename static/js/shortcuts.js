// ====== 可自定义快捷键系统 ======
// 绑定存到后端 app_config.shortcuts（JSON 字符串），格式 "Ctrl+Shift+K" / "Tab" / "F11"

const Shortcuts = {
  // scope: global = 全局；card = 剧本卡片编辑器
  ACTIONS: [
    { id: 'global.search',      label: '打开搜索',            def: 'Ctrl+P',        scope: 'global' },
    { id: 'global.focus',       label: '专注模式',            def: 'F11',           scope: 'global' },
    { id: 'global.prevChapter', label: '上一章 / 上一场',     def: 'Ctrl+ArrowUp',  scope: 'global' },
    { id: 'global.nextChapter', label: '下一章 / 下一场',     def: 'Ctrl+ArrowDown',scope: 'global' },
    { id: 'card.typeAction',    label: '当前卡片改为动作',    def: 'Ctrl+1',        scope: 'card' },
    { id: 'card.typeDialogue',  label: '当前卡片改为对白',    def: 'Ctrl+2',        scope: 'card' },
    { id: 'card.typeLyric',     label: '当前卡片改为唱词',    def: 'Ctrl+3',        scope: 'card' },
    { id: 'card.typeSong',      label: '当前卡片改为歌曲',    def: 'Ctrl+4',        scope: 'card' },
    { id: 'card.insert',        label: '插入新卡片（再按 1-4 选类型）', def: 'Ctrl+Shift+S', scope: 'card' },
    { id: 'card.delete',        label: '删除当前卡片',        def: 'Delete',        scope: 'card' },
    { id: 'card.switchChar',    label: '快速切换角色',        def: 'Ctrl+K',        scope: 'card' },
    { id: 'card.indent',        label: '移入上方歌曲',        def: 'Tab',           scope: 'card' },
    { id: 'card.outdent',       label: '移出歌曲',            def: 'Shift+Tab',     scope: 'card' },
  ],

  bindings: {}, // actionId -> combo；'' 表示未绑定

  // 从键盘事件生成组合键字符串；只按修饰键时返回 null
  comboFromEvent(e) {
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return null;
    const parts = [];
    if (e.ctrlKey || e.metaKey) parts.push('Ctrl');
    if (e.altKey) parts.push('Alt');
    if (e.shiftKey) parts.push('Shift');
    let key = e.key;
    if (key === ' ') key = 'Space';
    if (key.length === 1) key = key.toUpperCase();
    parts.push(key);
    return parts.join('+');
  },

  currentCombo(id) {
    const a = this.ACTIONS.find(x => x.id === id);
    if (!a) return '';
    return (this.bindings[id] !== undefined) ? this.bindings[id] : a.def;
  },

  // 事件匹配到哪个动作 id（匹配不到返回 null）
  actionFor(e) {
    const combo = this.comboFromEvent(e);
    if (!combo) return null;
    for (const a of this.ACTIONS) {
      const bound = (this.bindings[a.id] !== undefined) ? this.bindings[a.id] : a.def;
      if (bound && bound === combo) return a.id;
    }
    return null;
  },

  async load() {
    try {
      const cfg = await api._get('/api/config');
      if (cfg && cfg.shortcuts) {
        this.bindings = JSON.parse(cfg.shortcuts) || {};
      }
    } catch (err) { /* 配置不存在就用默认 */ }
  },

  async save() {
    try {
      await api._put('/api/config', { shortcuts: JSON.stringify(this.bindings) });
    } catch (err) {
      toast('快捷键保存失败', 'error');
    }
  },

  async resetAll() {
    this.bindings = {};
    await this.save();
  },

  // 设置某个动作的绑定；组合键冲突时把另一个动作置为未绑定
  async rebind(id, combo) {
    for (const a of this.ACTIONS) {
      if (a.id !== id && this.currentCombo(a.id) === combo) {
        this.bindings[a.id] = '';
        toast(`「${a.label}」的快捷键已被覆盖`, 'info');
      }
    }
    this.bindings[id] = combo;
    await this.save();
  },

  openSettings() {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;display:flex;align-items:center;justify-content:center;';

    const rows = this.ACTIONS.map(a => `
      <div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border-color);">
        <span style="flex:1;font-size:13px;">${escHtml(a.label)}
          <span style="font-size:11px;color:var(--text-muted);">${a.scope === 'global' ? '全局' : '剧本卡片'}</span>
        </span>
        <button class="sc-combo-btn" data-id="${a.id}" style="min-width:110px;padding:3px 10px;border:1px solid var(--border-color);border-radius:4px;font-size:12px;background:var(--bg-primary);cursor:pointer;">${escHtml(this.currentCombo(a.id)) || '未绑定'}</button>
        <button class="sc-clear-btn" data-id="${a.id}" title="清除绑定" style="padding:3px 8px;border:1px solid var(--border-color);border-radius:4px;font-size:12px;background:transparent;cursor:pointer;color:var(--text-muted);">×</button>
      </div>`).join('');

    overlay.innerHTML = `
      <div style="background:var(--bg-secondary);border-radius:10px;padding:20px 24px;width:480px;max-height:80vh;overflow-y:auto;box-shadow:0 8px 30px rgba(0,0,0,0.3);">
        <div style="display:flex;align-items:center;margin-bottom:8px;">
          <h3 style="flex:1;margin:0;font-size:16px;">快捷键设置</h3>
          <button id="sc-close" style="border:none;background:transparent;font-size:18px;cursor:pointer;color:var(--text-muted);">×</button>
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">点击右侧按钮后按下新的组合键即可修改；Esc 取消。</div>
        ${rows}
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
          <button id="sc-reset" style="padding:5px 14px;border:1px solid var(--border-color);border-radius:4px;font-size:12px;background:transparent;cursor:pointer;">恢复全部默认</button>
          <button id="sc-done" style="padding:5px 14px;border:none;border-radius:4px;font-size:12px;background:var(--accent);color:white;cursor:pointer;">完成</button>
        </div>
      </div>`;

    document.body.appendChild(overlay);
    const close = () => {
      // 关闭弹窗时取消未完成的按键捕获，避免残留监听器绑到已移除的按钮上
      if (this._cancelCapture) this._cancelCapture();
      overlay.remove();
    };
    overlay.querySelector('#sc-close').onclick = close;
    overlay.querySelector('#sc-done').onclick = close;
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#sc-reset').onclick = async () => {
      await this.resetAll();
      overlay.querySelectorAll('.sc-combo-btn').forEach(btn => {
        btn.textContent = this.currentCombo(btn.dataset.id) || '未绑定';
      });
      toast('已恢复默认快捷键');
    };

    overlay.querySelectorAll('.sc-clear-btn').forEach(btn => {
      btn.onclick = async () => {
        this.bindings[btn.dataset.id] = '';
        await this.save();
        overlay.querySelector(`.sc-combo-btn[data-id="${btn.dataset.id}"]`).textContent = '未绑定';
      };
    });

    overlay.querySelectorAll('.sc-combo-btn').forEach(btn => {
      btn.onclick = () => {
        // 已有其他按钮处于捕获态时先取消，避免一次按键同时绑定两个动作
        if (this._cancelCapture) this._cancelCapture();
        const id = btn.dataset.id;
        btn.textContent = '请按快捷键…';
        btn.style.borderColor = 'var(--accent)';
        const capture = (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (e.key === 'Escape') {
            endCapture();
            btn.textContent = this.currentCombo(id) || '未绑定';
            btn.style.borderColor = 'var(--border-color)';
            return;
          }
          const combo = this.comboFromEvent(e);
          if (!combo) return; // 只按了修饰键，继续等
          endCapture();
          this.rebind(id, combo).then(() => {
            // 刷新所有按钮（冲突的可能被清掉了）
            overlay.querySelectorAll('.sc-combo-btn').forEach(b => {
              b.textContent = this.currentCombo(b.dataset.id) || '未绑定';
              b.style.borderColor = 'var(--border-color)';
            });
          });
        };
        const endCapture = () => {
          document.removeEventListener('keydown', capture, true);
          this._cancelCapture = null;
        };
        this._cancelCapture = () => {
          endCapture();
          btn.textContent = this.currentCombo(id) || '未绑定';
          btn.style.borderColor = 'var(--border-color)';
        };
        document.addEventListener('keydown', capture, true);
      };
    });
  },
};
