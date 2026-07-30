// ====== 编辑器排版设置（字体/字号/行距/栏宽，localStorage 持久化）======

const EditorStyle = {
  defaults: { font: 'serif', size: 17, lineHeight: 1.9, width: 'full' },
  settings: null,

  fonts: {
    serif: '"Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif',
    sans: '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
    mono: '"Source Code Pro", "Courier New", "SimSun", monospace',
  },

  // 栏宽：限制编辑区最大宽度并居中
  widths: { full: '', wide: '1100px', medium: '860px', narrow: '680px' },

  labels: {
    font: { serif: '衬线（宋体系）', sans: '黑体（雅黑系）', mono: '等宽' },
    width: { full: '全宽', wide: '宽', medium: '适中', narrow: '窄' },
  },

  load() {
    try {
      this.settings = { ...this.defaults, ...(JSON.parse(localStorage.getItem('editorStyle')) || {}) };
    } catch (e) {
      this.settings = { ...this.defaults };
    }
  },

  save() {
    localStorage.setItem('editorStyle', JSON.stringify(this.settings));
  },

  apply() {
    const ed = document.getElementById('editor');
    if (!ed || !this.settings) return;
    ed.style.fontFamily = this.fonts[this.settings.font] || this.fonts.serif;
    ed.style.fontSize = this.settings.size + 'px';
    ed.style.lineHeight = this.settings.lineHeight;
    const mw = this.widths[this.settings.width] || '';
    ed.style.maxWidth = mw;
    ed.style.margin = mw ? '0 auto' : '';
  },

  set(key, value) {
    this.settings[key] = value;
    this.save();
    this.apply();
  },

  // 排版设置弹窗：改动即时预览并保存
  showDialog() {
    const s = this.settings;
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:360px;">
        <h3>排版设置</h3>
        <div class="form-group">
          <label>字体</label>
          <select id="es-font" style="width:100%;">
            ${Object.entries(this.labels.font).map(([k, v]) =>
              `<option value="${k}" ${s.font === k ? 'selected' : ''}>${v}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>字号：<span id="es-size-val">${s.size}</span> px</label>
          <input id="es-size" type="range" min="14" max="24" step="1" value="${s.size}" style="width:100%;padding:0;">
        </div>
        <div class="form-group">
          <label>行距</label>
          <select id="es-line-height" style="width:100%;">
            ${[1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2].map(v =>
              `<option value="${v}" ${Number(s.lineHeight) === v ? 'selected' : ''}>${v}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>栏宽</label>
          <select id="es-width" style="width:100%;">
            ${Object.entries(this.labels.width).map(([k, v]) =>
              `<option value="${k}" ${s.width === k ? 'selected' : ''}>${v}</option>`).join('')}
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn-primary">完成</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('#es-font').addEventListener('change', (e) => this.set('font', e.target.value));
    overlay.querySelector('#es-size').addEventListener('input', (e) => {
      overlay.querySelector('#es-size-val').textContent = e.target.value;
      this.set('size', parseInt(e.target.value));
    });
    overlay.querySelector('#es-line-height').addEventListener('change', (e) => this.set('lineHeight', parseFloat(e.target.value)));
    overlay.querySelector('#es-width').addEventListener('change', (e) => this.set('width', e.target.value));

    overlay.querySelector('.btn-primary').onclick = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') overlay.remove(); });
  },
};

document.addEventListener('DOMContentLoaded', () => {
  EditorStyle.load();
  EditorStyle.apply();
  document.getElementById('btn-editor-style')?.addEventListener('click', () => EditorStyle.showDialog());
});
