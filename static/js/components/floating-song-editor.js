// ====== 游离歌曲编辑器（音乐剧：不挂场、不进正文，仅出现在 JSON 导出） ======
// 元素模型与正文一致：顶层 lyrics 为 lyric/dialogue/ensemble 三种元素，
// ensemble 为重唱容器，children 内嵌唱词子卡（parent_id 指向容器 id）。

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

  // 按元素 id 在树中查找（ensemble 的 children 也参与查找）
  findElem(id) {
    const walk = (list) => {
      for (const e of (list || [])) {
        if (e.id === id) return e;
        const found = walk(e.children);
        if (found) return found;
      }
      return null;
    };
    return walk(this.currentSong?.lyrics);
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

    for (const elem of (song.lyrics || [])) {
      html += this.renderElement(elem, 0);
    }

    // 底部添加按钮：唱词 / 对白 / 重唱
    html += `<div style="text-align:center;margin-top:8px;">
      <button class="fsong-add-elem" data-type="lyric" style="margin:4px;padding:6px 14px;border:1px dashed var(--border-color);border-radius:6px;font-size:13px;cursor:pointer;">+ 🎤 唱词</button>
      <button class="fsong-add-elem" data-type="dialogue" style="margin:4px;padding:6px 14px;border:1px dashed var(--border-color);border-radius:6px;font-size:13px;cursor:pointer;">+ 💬 对白</button>
      <button class="fsong-add-elem" data-type="ensemble" style="margin:4px;padding:6px 14px;border:1px dashed #f0c080;border-radius:6px;font-size:13px;cursor:pointer;">+ 🎼 重唱</button>
    </div>`;

    wrap.innerHTML = html;
    this.bindEvents(wrap);
  },

  // 渲染单个元素（lyric 唱词卡 / dialogue 对白卡 / ensemble 重唱容器）
  renderElement(elem, depth) {
    const marginLeft = depth * 24;
    const names = this.charNames(elem.character_ids);
    const delBtn = `<button class="fsong-elem-del" data-id="${elem.id}" data-type="${elem.element_type}" style="font-size:14px;padding:0 4px;color:var(--danger);opacity:0.5;" title="删除">×</button>`;

    if (elem.element_type === 'ensemble') {
      // 重唱容器：标题 + 缩进的唱词子卡 + 容器内添加唱词按钮
      let html = `<div class="fsong-elem" data-id="${elem.id}" style="margin-bottom:8px;margin-left:${marginLeft}px;background:#fff3e0;border:1px solid #f0c080;border-radius:8px;overflow:hidden;">
        <div style="display:flex;align-items:center;padding:6px 10px;gap:8px;font-size:12px;border-bottom:1px solid var(--border-color);">
          <span style="font-size:13px;font-weight:bold;color:#c8801a;">🎼 重唱（多人同时唱不同的词）</span>
          <span style="flex:1;"></span>
          ${delBtn}
        </div>
      </div>`;
      for (const child of (elem.children || [])) {
        html += this.renderElement(child, depth + 1);
      }
      html += `<div style="margin-left:${(depth + 1) * 24}px;margin-bottom:8px;text-align:center;">
        <button class="fsong-add-child-lyric" data-id="${elem.id}" style="margin:2px;padding:4px 10px;border:1px dashed var(--border-color);border-radius:4px;font-size:11px;">+ 🎤 唱词</button>
      </div>`;
      return html;
    }

    if (elem.element_type === 'dialogue') {
      // 歌中对白：单角色下拉（统一存 character_ids 数组）
      const curId = (elem.character_ids || [])[0] || '';
      return `<div class="fsong-elem" data-id="${elem.id}" style="margin-bottom:8px;margin-left:${marginLeft}px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">
        <div style="display:flex;align-items:center;padding:6px 10px;gap:8px;font-size:12px;border-bottom:1px solid var(--border-color);">
          <span>💬</span>
          <select class="fsong-dialogue-char" data-id="${elem.id}" style="border:none;background:transparent;font-size:12px;min-width:80px;">
            <option value="">选择角色</option>
            ${this.characterList.map(c => `<option value="${c.id}" ${c.id === curId ? 'selected' : ''}>${escHtml(c.name)}</option>`).join('')}
          </select>
          <span style="flex:1;"></span>
          ${delBtn}
        </div>
        <textarea class="fsong-elem-content" data-id="${elem.id}" placeholder="对白内容..." style="width:100%;border:none;resize:vertical;min-height:40px;padding:8px 10px;font-size:14px;line-height:1.6;background:transparent;">${escHtml(elem.content || '')}</textarea>
      </div>`;
    }

    // 唱词卡：演唱者多选（合唱）
    return `<div class="fsong-elem" data-id="${elem.id}" style="margin-bottom:8px;margin-left:${marginLeft}px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">
      <div style="display:flex;align-items:center;padding:6px 10px;gap:8px;font-size:12px;border-bottom:1px solid var(--border-color);">
        <span>🎤</span>
        <button class="fsong-singers" data-id="${elem.id}" title="选择演唱者" style="border:1px dashed var(--border-color);background:transparent;font-size:12px;padding:2px 8px;border-radius:4px;cursor:pointer;">${escHtml(names) || '选择演唱者'} ▾</button>
        <span style="flex:1;"></span>
        ${delBtn}
      </div>
      <textarea class="fsong-elem-content" data-id="${elem.id}" placeholder="唱词内容..." style="width:100%;border:none;resize:vertical;min-height:40px;padding:8px 10px;font-size:14px;line-height:1.6;background:transparent;">${escHtml(elem.content || '')}</textarea>
    </div>`;
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

    // 添加顶层元素：唱词 / 对白 / 重唱
    wrap.querySelectorAll('.fsong-add-elem').forEach(btn => {
      btn.addEventListener('click', async () => {
        await api.floatingSong.addLyric(song.id, { elementType: btn.dataset.type, content: '' });
        await this.open(song.id);
      });
    });

    // 重唱容器内添加唱词（parent_id 指向容器）
    wrap.querySelectorAll('.fsong-add-child-lyric').forEach(btn => {
      btn.addEventListener('click', async () => {
        await api.floatingSong.addLyric(song.id, { elementType: 'lyric', parentId: parseInt(btn.dataset.id), content: '' });
        await this.open(song.id);
      });
    });

    // 演唱者多选（同正文唱词的合唱选择）
    wrap.querySelectorAll('.fsong-singers').forEach(btn => {
      btn.addEventListener('click', async () => {
        const elem = this.findElem(parseInt(btn.dataset.id));
        if (!elem) return;
        const options = this.characterList.map(c => ({ id: c.id, label: c.name }));
        const ids = await uiChecklist('选择演唱者', options, elem.character_ids || []);
        if (ids === null) return;
        elem.character_ids = ids;
        await api.floatingSong.updateLyric(elem.id, { characterIds: ids });
        this.render();
      });
    });

    // 对白角色单选（统一存 character_ids 数组）
    wrap.querySelectorAll('.fsong-dialogue-char').forEach(sel => {
      sel.addEventListener('change', async () => {
        const elem = this.findElem(parseInt(sel.dataset.id));
        const cid = sel.value ? parseInt(sel.value) : null;
        const ids = cid ? [cid] : [];
        if (elem) elem.character_ids = ids;
        await api.floatingSong.updateLyric(parseInt(sel.dataset.id), { characterIds: ids });
      });
    });

    // 内容防抖保存（唱词与对白通用）
    wrap.querySelectorAll('.fsong-elem-content').forEach(ta => {
      const lid = parseInt(ta.dataset.id);
      ta.addEventListener('input', debounce(async () => {
        const elem = this.findElem(lid);
        if (!elem || ta.value === elem.content) return;
        elem.content = ta.value;
        await api.floatingSong.updateLyric(lid, { content: ta.value });
      }, 1000));
    });

    // 删除元素（ensemble 级联删除子唱词）
    wrap.querySelectorAll('.fsong-elem-del').forEach(btn => {
      btn.addEventListener('click', async () => {
        const type = btn.dataset.type;
        const msg = type === 'ensemble'
          ? '删除这个重唱容器吗？其中的所有唱词将一并删除。'
          : (type === 'dialogue' ? '删除这条对白吗？' : '删除这条唱词吗？');
        if (!await uiConfirm(msg, { danger: true, okText: '删除' })) return;
        await api.floatingSong.deleteLyric(parseInt(btn.dataset.id));
        await this.open(song.id);
      });
    });
  },
};
