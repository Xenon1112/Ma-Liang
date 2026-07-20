// ====== 导出对话框 ======

const ExportDialog = {
  async show() {
    const projectId = AppState.currentProject?.id;
    if (!projectId) { toast('请先打开作品', 'error'); return; }

    const chapterId = AppState.currentChapter?.id;
    const project = AppState.currentProject;
    const ext = 'txt';
    const namePart = chapterId ? (AppState.currentChapter?.title || 'chapter') : (project.title || 'export');

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal" style="min-width:450px;">
        <h3>导出</h3>
        <div class="form-group">
          <label>导出范围</label>
          <select id="export-scope">
            <option value="project">全部章节</option>
            ${chapterId ? '<option value="chapter">当前章节</option>' : ''}
          </select>
        </div>
        <div class="form-group">
          <label>导出格式</label>
          <select id="export-format">
            <option value="txt">TXT 文本文件</option>
            <option value="docx">Word 文档 (.docx)</option>
          </select>
        </div>
        <div class="form-group">
          <label>保存路径</label>
          <input id="export-path" type="text" placeholder="例如: C:/Users/xxx/Desktop/${namePart}.${ext}" style="width:100%;">
        </div>
        <div id="export-docx-options" style="display:none;">
          <div class="form-group">
            <label>字体</label>
            <select id="export-font">
              <option value="SimSun">宋体</option>
              <option value="SimHei">黑体</option>
              <option value="KaiTi">楷体</option>
              <option value="Microsoft YaHei">微软雅黑</option>
            </select>
          </div>
          <div class="form-group">
            <label>字号 (pt)</label>
            <input id="export-font-size" type="number" value="12" min="8" max="24" style="width:100%;">
          </div>
          <div class="form-group">
            <label>行距</label>
            <select id="export-line-spacing">
              <option value="1">单倍</option>
              <option value="1.5" selected>1.5 倍</option>
              <option value="2">双倍</option>
            </select>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel">取消</button>
          <button class="btn-primary" id="btn-do-export">导出</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector('.btn-cancel').onclick = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    // 格式切换
    document.getElementById('export-format').addEventListener('change', function() {
      document.getElementById('export-docx-options').style.display = this.value === 'docx' ? 'block' : 'none';
      const newExt = this.value === 'docx' ? 'docx' : 'txt';
      document.getElementById('export-path').placeholder = `例如: C:/Users/xxx/Desktop/${namePart}.${newExt}`;
    });

    document.getElementById('btn-do-export').onclick = async () => {
      const scope = document.getElementById('export-scope').value;
      const format = document.getElementById('export-format').value;
      const filePath = document.getElementById('export-path').value.trim();
      if (!filePath) { toast('请输入保存路径', 'error'); return; }

      try {
        if (format === 'txt') {
          const params = { outputPath: filePath };
          if (scope === 'chapter') params.chapterId = chapterId;
          else params.projectId = projectId;
          await api.export.toTxt(params);
        } else {
          const params = {
            outputPath: filePath,
            options: {
              font: document.getElementById('export-font').value,
              fontSize: parseInt(document.getElementById('export-font-size').value),
              lineSpacing: parseFloat(document.getElementById('export-line-spacing').value),
            },
          };
          if (scope === 'chapter') params.chapterId = chapterId;
          else params.projectId = projectId;
          await api.export.toDocx(params);
        }
        toast('导出成功', 'success');
        overlay.remove();
      } catch (err) {
        toast('导出失败: ' + err.message, 'error');
      }
    };
  },
};
