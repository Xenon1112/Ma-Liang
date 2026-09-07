// 乐谱（MuseScore）共享逻辑：打开乐谱、未安装引导、MuseScore 路径设置弹窗
// 供 CardEditor（正文歌曲卡片）与 FloatingSongEditor（游离歌曲）共用
// (G3 由 static/js/components/score-helper.js 迁入,逻辑不变;末尾留 window 别名)
NW.plugins.score = {

  // 打开某首歌曲的乐谱；target 为 { elementId } 或 { floatingSongId }，外加 songTitle
  async openScore(target) {
    const projectId = AppState.currentProject?.id;
    if (!projectId) return false;
    try {
      const r = await api.score.open({ projectId, ...target });
      toast(r.created ? '已创建乐谱并在 MuseScore 中打开' : '已在 MuseScore 中打开乐谱');
      return true;
    } catch (err) {
      const goSettings = await uiConfirm(
        (err.message || '打开乐谱失败') + '。要现在配置 MuseScore 路径吗？',
        { okText: '去设置' });
      if (goSettings) this.openSettings();
      return false;
    }
  },

  // MuseScore 路径设置弹窗（配置存 app_config 的 musescorePath,写入仍走内核 /api/config）
  async openSettings() {
    const [config, detect] = await Promise.all([api.app.getConfig(), api.score.detectPath()]);

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `
      <div style="background:var(--bg-secondary);border-radius:10px;padding:20px 24px;width:520px;box-shadow:0 8px 30px rgba(0,0,0,0.3);">
        <div style="display:flex;align-items:center;margin-bottom:12px;">
          <h3 style="flex:1;margin:0;font-size:16px;">MuseScore 设置</h3>
          <button id="ms-close" style="border:none;background:transparent;font-size:18px;cursor:pointer;color:var(--text-muted);">×</button>
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">
          乐谱编辑由本机安装的 MuseScore 4 完成。尚未安装请先到
          <a href="https://musescore.org" target="_blank" style="color:var(--accent);">musescore.org</a> 下载（免费）。
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input id="ms-path" value="${escAttr(config.musescorePath || '')}" placeholder="MuseScore 可执行文件路径（留空则自动探测）"
            style="flex:1;padding:6px 10px;border:1px solid var(--border-color);border-radius:4px;font-size:13px;background:var(--bg-primary);color:var(--text-primary);">
          <button id="ms-detect" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:4px;font-size:12px;background:transparent;cursor:pointer;">自动探测</button>
        </div>
        <div id="ms-status" style="font-size:12px;margin-top:8px;color:${detect.current ? 'var(--accent)' : 'var(--danger)'};">
          ${detect.current ? '当前可用：' + escHtml(detect.current) : '当前未找到可用的 MuseScore'}
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
          <button id="ms-save" style="padding:5px 14px;border:none;border-radius:4px;font-size:12px;background:var(--accent);color:white;cursor:pointer;">保存</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#ms-close').onclick = close;
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });

    overlay.querySelector('#ms-detect').onclick = async () => {
      const d = await api.score.detectPath();
      if (d.detected) {
        overlay.querySelector('#ms-path').value = d.detected;
        overlay.querySelector('#ms-status').textContent = '探测到：' + d.detected;
      } else {
        overlay.querySelector('#ms-status').textContent = '未探测到 MuseScore，请手动填写路径';
      }
    };

    overlay.querySelector('#ms-save').onclick = async () => {
      await api.app.setConfig({ musescorePath: overlay.querySelector('#ms-path').value.trim() });
      toast('MuseScore 路径已保存');
      close();
    };
  },
};

const ScoreHelper = NW.plugins.score;
window.ScoreHelper = ScoreHelper;
