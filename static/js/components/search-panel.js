// ====== 全局搜索 ======

const SearchPanel = {
  visible: false,
  searchSeq: 0,

  show() {
    if (this.visible) return;
    this.visible = true;

    const overlay = document.createElement('div');
    overlay.id = 'search-overlay';
    overlay.innerHTML = `
      <div id="search-panel">
        <div class="search-input-wrap">
          <span>🔍</span>
          <input id="search-input" type="text" placeholder="搜索所有内容... (Esc 关闭)" autofocus>
        </div>
        <div class="search-results" id="search-results">
          <p style="color:var(--text-muted);text-align:center;padding:20px;">输入关键词开始搜索</p>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const input = document.getElementById('search-input');
    input.focus();

    let searchTimer;
    input.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => this.doSearch(input.value.trim()), 300);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.hide();
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) this.hide();
    });
  },

  hide() {
    this.visible = false;
    const overlay = document.getElementById('search-overlay');
    if (overlay) overlay.remove();
  },

  async doSearch(keyword) {
    const seq = ++this.searchSeq;
    const resultsDiv = document.getElementById('search-results');
    if (!keyword) {
      resultsDiv.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px;">输入关键词开始搜索</p>';
      return;
    }

    const projectId = AppState.currentProject?.id;
    if (!projectId) {
      resultsDiv.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px;">请先打开一个作品</p>';
      return;
    }

    const results = await api.search.fullText(projectId, keyword);
    if (seq !== this.searchSeq) return; // 已有更新的搜索请求，丢弃过期响应

    if (results.length === 0) {
      resultsDiv.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px;">未找到结果</p>';
      return;
    }

    const typeLabels = { chapter:'章节', outline:'大纲', character:'人物', world_setting:'设定', inspiration:'灵感', scene:'场景', floating_song:'歌曲' };

    resultsDiv.innerHTML = results.map(r => `
      <div class="search-result-item" data-type="${r.type}" data-id="${r.id}">
        <div class="result-type">${typeLabels[r.type] || r.type}</div>
        <div class="result-title">${escHtml(r.title)}</div>
        ${r.subtitle ? `<div class="result-subtitle">${escHtml(r.subtitle)}</div>` : ''}
        <div class="result-snippet">${highlightKeyword(r.snippet, keyword)}</div>
      </div>
    `).join('');

    // 点击结果跳转
    resultsDiv.querySelectorAll('.search-result-item').forEach(item => {
      item.addEventListener('click', async () => {
        const type = item.dataset.type;
        const id = parseInt(item.dataset.id);
        this.hide();

        if (type === 'chapter') {
          try {
            const chapter = await api.chapter.get(id);
            if (chapter) {
              const vol = await api.volume.get(chapter.volume_id);
              if (vol) AppState.setVolume(vol);
              AppState.setChapter(chapter);
              Editor.loadChapter(id);
            }
          } catch (err) {
            toast('该章节所在卷已被删除', 'error');
          }
        } else if (type === 'character') {
          AppState.rightPanelTab = 'character';
          switchRightTab('character');
          CharacterPanel.selectChar(id);
        } else if (type === 'world_setting') {
          AppState.rightPanelTab = 'world';
          switchRightTab('world');
          WorldSettingPanel.refresh();
        } else if (type === 'outline') {
          AppState.rightPanelTab = 'outline';
          switchRightTab('outline');
          OutlinePanel.refresh();
        } else if (type === 'scene') {
          // 剧本场结果：从侧栏缓存中找到该场所在幕，展开后加载并高亮
          let act = null;
          let sc = null;
          for (const a of (ScriptSidebar.actData || [])) {
            const found = (a.scenes || []).find(s => s.id === id);
            if (found) { act = a; sc = found; break; }
          }
          if (sc) {
            AppState.currentAct = act;
            AppState.currentScene = sc;
            ScriptSidebar.collapsedActs[act.id] = false;
            FloatingSongEditor.clear();
            CardEditor.loadScene(id);
            ScriptSidebar.render();
          } else {
            toast('该场已被删除', 'error');
          }
        } else if (type === 'floating_song') {
          // 游离歌曲结果：打开游离歌曲编辑器并刷新侧栏高亮
          await FloatingSongEditor.open(id);
          ScriptSidebar.render();
        } else if (type === 'inspiration') {
          AppState.rightPanelTab = 'inspiration';
          switchRightTab('inspiration');
          InspirationPanel.refresh();
        }
      });
    });
  },
};

function highlightKeyword(text, keyword) {
  if (!text || !keyword) return escHtml(text || '');
  const escaped = escHtml(text);
  const kwEscaped = escHtml(keyword);
  return escaped.replace(new RegExp(kwEscaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), '<mark>$&</mark>');
}
