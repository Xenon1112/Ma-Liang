// ====== 游离歌曲编辑器（音乐剧：不挂场、不进正文，仅出现在 JSON 导出） ======

const FloatingSongEditor = {
  currentSong: null,
  characterList: [],

  async open(songId) {
    // 与正文卡片编辑器互斥
    CardEditor.clear();
    AppState.currentScene = null;
    const projectId = AppState.currentProject?.id;
    if (!projectId) return;
    const songs = await api.floatingSong.list(projectId);
    this.currentSong = songs.find(s => s.id === songId) || null;
    if (!this.currentSong) { ScriptSidebar.refresh(); return; }
    this.characterList = await api.character.list(projectId);
    document.getElementById('breadcrumb-vol').textContent = this.currentSong.song_title;
    document.getElementById('breadcrumb-ch').textContent = '🎵 游离歌曲';
    this.render();
  },

  clear() {
    this.currentSong = null;
    const wrap = document.getElementById('card-editor-wrap');
    if (wrap) wrap.innerHTML = '';
  },

  charNames(ids) {
    return (ids || []).map(id => this.characterList.find(c => c.id === id)?.name).filter(Boolean).join('、');
  },

  render() {
    const song = this.currentSong;
    if (!song) return;

    // 复用 card-editor-wrap（不存在则创建，与 CardEditor 同一容器）
    const textarea = document.getElementById('editor');
    if (textarea) textarea.style.display = 'none';
    let wrap = document.getElementById('card-editor-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = 'card-editor-wrap';
      wrap.style.cssText = 'flex:1;overflow-y:auto;padding:16px 24px;background:var(--editor-bg);';
      document.getElementById('editor-container').appendChild(wrap);
    }
    wrap.style.display = '';

    let html = `<div style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;padding:12px 16px;margin-bottom:16px;">
      <div style="display:flex;gap:12px;align-items:center;">
        <span style="font-size:16px;">🎵</span>
        <input id="fsong-title-input" value="${escAttr(song.song_title || '')}" placeholder="歌曲名" style="flex:1;font-size:16px;font-weight:bold;">
        <button id="fsong-move-btn" style="padding:4px 12px;border:1px solid var(--accent);color:var(--accent);border-radius:4px;font-size:12px;background:transparent;cursor:pointer;">挂到某场…</button>
        <button id="fsong-save-btn" style="padding:4px 12px;background:var(--accent);color:white;border-radius:4px;font-size:12px;">保存歌名</button>
      </div>
      <div style="margin-top:6px;font-size:12px;color:var(--text-muted);">游离歌曲不出现在正文与 TXT/DOCX 导出中，仅包含在 JSON 导出里。</div>
    </div>`;

    for (const l of (song.lyrics || [])) {
      const names = this.charNames(l.character_ids);
      html += `<div class="fsong-lyric" data-id="${l.id}" style="margin-bottom:8px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">
        <div style="display:flex;align-items:center;padding:6px 10px;gap:8px;font-size:12px;border-bottom:1px solid var(--border-color);">
          <span>🎤</span>
          <button class="fsong-singers" data-id="${l.id}" title="选择演唱者" style="border:1px dashed var(--border-color);background:transparent;font-size:12px;padding:2px 8px;border-radius:4px;cursor:pointer;">${escHtml(names) || '选择演唱者'} ▾</button>
          <span style="flex:1;"></span>
          <button class="fsong-lyric-del" data-id="${l.id}" style="font-size:14px;padding:0 4px;color:var(--danger);opacity:0.5;" title="删除唱词">×</button>
        </div>
        <textarea class="fsong-lyric-content" data-id="${l.id}" placeholder="唱词内容..." style="width:100%;border:none;resize:vertical;min-height:40px;padding:8px 10px;font-size:14px;line-height:1.6;background:transparent;">${escHtml(l.content || '')}</textarea>
      </div>`;
    }

    html += `<div style="text-align:center;margin-top:8px;">
      <button id="fsong-add-lyric" style="margin:4px;padding:6px 14px;border:1px dashed var(--border-color);border-radius:6px;font-size:13px;cursor:pointer;">+ 🎤 添加唱词</button>
    </div>`;

    wrap.innerHTML = html;
    this.bindEvents(wrap);
  },

  bindEvents(wrap) {
    const song = this.currentSong;

    // 挂到某场（转为正文歌曲）
    wrap.querySelector('#fsong-move-btn').onclick = () => moveFloatingToScene(song.id);

    // 歌名保存（失焦自动保存）
    wrap.querySelector('#fsong-save-btn').onclick = async () => {
      const title = wrap.querySelector('#fsong-title-input').value.trim();
      await api.floatingSong.update(song.id, { songTitle: title });
      song.song_title = title;
      document.getElementById('breadcrumb-vol').textContent = title;
      toast('歌名已保存');
      ScriptSidebar.refresh();
    };
    wrap.querySelector('#fsong-title-input').addEventListener('blur', () => {
      wrap.querySelector('#fsong-save-btn').click();
    });

    // 添加唱词
    wrap.querySelector('#fsong-add-lyric').onclick = async () => {
      await api.floatingSong.addLyric(song.id, { content: '' });
      await this.open(song.id);
    };

    // 演唱者多选（同正文唱词的合唱选择）
    wrap.querySelectorAll('.fsong-singers').forEach(btn => {
      btn.addEventListener('click', async () => {
        const lyric = song.lyrics.find(l => l.id === parseInt(btn.dataset.id));
        if (!lyric) return;
        const options = this.characterList.map(c => ({ id: c.id, label: c.name }));
        const ids = await uiChecklist('选择演唱者', options, lyric.character_ids || []);
        if (ids === null) return;
        lyric.character_ids = ids;
        await api.floatingSong.updateLyric(lyric.id, { characterIds: ids });
        this.render();
      });
    });

    // 唱词内容防抖保存
    wrap.querySelectorAll('.fsong-lyric-content').forEach(ta => {
      const lid = parseInt(ta.dataset.id);
      ta.addEventListener('input', debounce(async () => {
        const lyric = song.lyrics.find(l => l.id === lid);
        if (!lyric || ta.value === lyric.content) return;
        lyric.content = ta.value;
        await api.floatingSong.updateLyric(lid, { content: ta.value });
      }, 1000));
    });

    // 删除唱词
    wrap.querySelectorAll('.fsong-lyric-del').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!await uiConfirm('删除这条唱词吗？', { danger: true, okText: '删除' })) return;
        await api.floatingSong.deleteLyric(parseInt(btn.dataset.id));
        await this.open(song.id);
      });
    });
  },
};
