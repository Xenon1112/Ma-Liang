// ====== 导出对话框 ======

NW.plugins.export = {
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
            <option value="json">JSON 项目文件（整项目，不含回收站）</option>
          </select>
        </div>
        <div id="export-json-note" style="display:none;color:var(--text-muted);font-size:12px;margin:-4px 0 8px;">
          JSON 导出包含整个项目（全部章节、草稿版本、人物、设定等），不含回收站；仅支持全书导出，即使当前选中了单个章节也会导出整本书；导入时会生成副本。
        </div>
        <div class="form-group">
          <label>保存路径（留空自动保存到桌面）</label>
          <input id="export-path" type="text" placeholder="留空 → 桌面/${escAttr(namePart)}.${ext}；也可填目录或完整路径" style="width:100%;">
        </div>
        <div id="export-docx-options" style="display:none;">
          <div class="form-group">
            <label>字体</label>
            <select id="export-font">
              <option value="SimSun">宋体</option>
              <option value="SimHei">黑体</option>
              <option value="KaiTi">楷体</option>
              <option value="FangSong">仿宋</option>
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
      document.getElementById('export-json-note').style.display = this.value === 'json' ? 'block' : 'none';
      const newExt = this.value === 'docx' ? 'docx' : this.value === 'json' ? 'json' : 'txt';
      document.getElementById('export-path').placeholder = `留空 → 桌面/${namePart}.${newExt}；也可填目录或完整路径`;
    });

    document.getElementById('btn-do-export').onclick = async () => {
      const scope = document.getElementById('export-scope').value;
      const format = document.getElementById('export-format').value;
      const filePath = document.getElementById('export-path').value.trim();

      try {
        let result;
        if (format === 'json') {
          // JSON 仅支持全书导出，忽略导出范围
          result = await api.export.exportJson(projectId, filePath);
        } else if (format === 'txt') {
          const params = { outputPath: filePath };
          if (scope === 'chapter') params.chapterId = chapterId;
          else params.projectId = projectId;
          result = await api.export.toTxt(params);
        } else {
          const params = {
            outputPath: filePath,
            options: {
              font: document.getElementById('export-font').value,
              fontSize: parseInt(document.getElementById('export-font-size').value) || 12,
              lineSpacing: parseFloat(document.getElementById('export-line-spacing').value),
            },
          };
          if (scope === 'chapter') params.chapterId = chapterId;
          else params.projectId = projectId;
          result = await api.export.toDocx(params);
        }
        toast('已导出: ' + result.filePath, 'success');
        overlay.remove();
      } catch (err) {
        toast('导出失败: ' + err.message, 'error');
      }
    };
  },
};

// 迁移期兼容别名:未迁移组件(app.js 等)仍用全局名引用本组件
const ExportDialog = NW.plugins.export;
window.ExportDialog = ExportDialog;
