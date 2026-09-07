// ====== 卡片编辑器 ======

NW.plugins.script = NW.plugins.script || {};
NW.plugins.script.cardEditor = {
  elements: [],
  flatElements: [],
  currentSceneId: null,
  selectedCardIndex: -1,
  characterList: [],
  // 歌曲收起状态（歌曲id → bool）：纯前端状态，不触发保存/刷新，localStorage 持久化
  collapsedSongs: null,

  // 从 localStorage 恢复歌曲收起状态（存的是已收起歌曲 id 的 JSON 数组）
  loadCollapsedSongs() {
    this.collapsedSongs = {};
    try {
      const ids = JSON.parse(localStorage.getItem('cardEditor.collapsedSongs') || '[]');
      for (const id of ids) this.collapsedSongs[id] = true;
    } catch (e) { /* localStorage 不可用或数据损坏时按全部展开处理 */ }
  },

  // 写回 localStorage（JSON 数组，只存已收起的歌曲 id）
  saveCollapsedSongs() {
    try {
      const ids = Object.keys(this.collapsedSongs).filter(id => this.collapsedSongs[id]);
      localStorage.setItem('cardEditor.collapsedSongs', JSON.stringify(ids));
    } catch (e) { /* 忽略持久化失败，不影响本次收起 */ }
  },

  // 切换歌曲收起状态（纯前端，不发任何请求）
  toggleSongCollapsed(songId) {
    if (this.collapsedSongs === null) this.loadCollapsedSongs();
    this.collapsedSongs[songId] = !this.collapsedSongs[songId];
    this.saveCollapsedSongs();
  },

  // 歌曲卡片头部右键菜单（样式参照 script-sidebar.js 的 showScriptContextMenu）
  showSongContextMenu(x, y, card) {
    const old = document.querySelector('.context-menu');
    if (old) old.remove();

    const collapsed = !!((this.collapsedSongs || {})[card.id]);
    const items = [
      // 第一项按当前状态动态显示收起/展开（纯前端状态，不触发保存/刷新）
      { label: collapsed ? '展开歌曲' : '收起歌曲', action: () => { this.toggleSongCollapsed(card.id); this.render(); } },
    ];
    // 转为游离歌曲：仅音乐剧项目的顶层歌曲（与头部「⇱ 游离」按钮同一逻辑）
    if (AppState.currentProject?.project_type === 'musical' && !card.parent_id) {
      items.push({ label: '转为游离歌曲…', action: () => this.convertSongToFloating(card) });
    }

    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:6px;box-shadow:var(--shadow);z-index:500;min-width:140px;padding:4px;font-size:13px;`;
    menu.innerHTML = items.map(it => `
      <div class="ctx-item" style="padding:6px 12px;border-radius:4px;cursor:pointer;">${it.label}</div>
    `).join('');
    document.body.appendChild(menu);

    // 防止菜单超出窗口右/下边缘：贴边时向左/向上偏移
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) menu.style.left = Math.max(0, window.innerWidth - rect.width - 4) + 'px';
    if (rect.bottom > window.innerHeight) menu.style.top = Math.max(0, window.innerHeight - rect.height - 4) + 'px';

    menu.querySelectorAll('.ctx-item').forEach((el, i) => {
      el.addEventListener('click', () => { menu.remove(); items[i].action(); });
      el.addEventListener('mouseenter', () => el.style.background = 'var(--bg-hover)');
      el.addEventListener('mouseleave', () => el.style.background = 'transparent');
    });
    setTimeout(() => document.addEventListener('click', function c(e) { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', c); } }), 0);
  },

  // 歌曲转游离歌曲（移出正文，仅保留在 JSON 导出）；头部「⇱ 游离」按钮与右键菜单共用
  async convertSongToFloating(card) {
    if (!await uiConfirm('将此歌曲转为游离歌曲？将从正文移除（唱词、歌中对白与重唱均保留，仅出现在 JSON 导出）。', { okText: '转换' })) return;
    try {
      await api.element.moveToFloating(card.id);
      toast('已转为游离歌曲');
      await this.loadScene(this.currentSceneId);
      ScriptSidebar.refresh();
    } catch (err) {
      toast('转换失败: ' + err.message, 'error');
    }
  },

  // 将树形元素展开为前序扁平列表，卡片 data-index 统一对应 flatElements
  flattenElements() {
    this.flatElements = [];
    const walk = (list) => {
      for (const e of list) {
        this.flatElements.push(e);
        if (e.children && e.children.length) walk(e.children);
      }
    };
    walk(this.elements);
  },

  getCard(idx) {
    return (idx >= 0 && idx < this.flatElements.length) ? this.flatElements[idx] : null;
  },

  async loadScene(sceneId) {
    this.currentSceneId = sceneId;
    const scene = await api.scene.get(sceneId);
    if (!scene) return;

    AppState.currentScene = scene;
    document.getElementById('breadcrumb-ch').textContent = scene.title;
    document.getElementById('breadcrumb-vol').textContent = AppState.currentAct?.title || '';

    // 加载角色列表
    const projectId = AppState.currentProject?.id;
    this.characterList = await api.character.list(projectId);

    // 加载元素
    this.elements = await api.element.list(sceneId);
    this.selectedCardIndex = -1;
    this.render();
    // 编辑区头部与侧栏同步显示当前场总字数
    this.updateSceneWordCount();
  },

  // 统计当前场全部卡片（正文 content + 歌名 song_title）的字数，
  // 局部同步到编辑区头部与侧栏该场节点，不做整树刷新
  updateSceneWordCount() {
    let text = '';
    for (const el of this.flatElements) {
      text += (el.content || '') + (el.song_title || '');
    }
    const { chinese, total } = countWords(text);
    const zhEl = document.getElementById('word-count-chinese');
    if (zhEl) zhEl.textContent = chinese;
    const totalEl = document.getElementById('word-count-total');
    if (totalEl) totalEl.textContent = total;
    // 侧栏该场节点字数局部更新
    const node = document.querySelector(`#tree-container .tree-node[data-type="scene"][data-id="${this.currentSceneId}"] .node-wordcount`);
    if (node) node.textContent = `${total} 字`;
    // 同步侧栏缓存数据，避免下次整树渲染时用旧值覆盖
    for (const act of (ScriptSidebar.actData || [])) {
      const sc = (act.scenes || []).find(s => s.id === this.currentSceneId);
      if (sc) { sc.word_count = total; break; }
    }
  },

  clear() {
    this.elements = [];
    this.currentSceneId = null;
    this.selectedCardIndex = -1;
    const area = document.getElementById('editor-area');
    if (document.getElementById('card-editor-wrap')) {
      document.getElementById('card-editor-wrap').innerHTML = '';
    }
    // 编辑区头部字数归零（剧本模式显示当前场总字数）
    const zhEl = document.getElementById('word-count-chinese');
    if (zhEl) zhEl.textContent = '0';
    const totalEl = document.getElementById('word-count-total');
    if (totalEl) totalEl.textContent = '0';
  },

  render() {
    const area = document.getElementById('editor-area');
    const scene = AppState.currentScene;
    const scriptType = AppState.currentProject?.project_type || 'play';
    const isMusical = scriptType === 'musical';

    // 首次渲染时从 localStorage 恢复歌曲收起状态（按歌曲 id 记忆，loadScene 后保持）
    if (this.collapsedSongs === null) this.loadCollapsedSongs();

    // 确保有 card-editor-wrap
    let wrap = document.getElementById('card-editor-wrap');
    if (!wrap) {
      // 隐藏 textarea
      const textarea = document.getElementById('editor');
      if (textarea) textarea.style.display = 'none';

      wrap = document.createElement('div');
      wrap.id = 'card-editor-wrap';
      wrap.style.cssText = 'flex:1;overflow-y:auto;padding:16px 24px;background:var(--editor-bg);';
      document.getElementById('editor-container').appendChild(wrap);
    }

    let html = '';

    // 场景信息栏
    html += `<div id="scene-info-bar" style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;padding:12px 16px;margin-bottom:16px;">
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:8px;">
        <input id="scene-title-input" value="${escAttr(scene?.title || '')}" placeholder="场名" style="flex:1;font-size:16px;font-weight:bold;">
        <button id="scene-save-btn" style="padding:4px 12px;background:var(--accent);color:white;border-radius:4px;font-size:12px;">保存</button>
      </div>
      <textarea id="scene-setting-input" placeholder="场景描述（时间、地点、环境...）" style="width:100%;min-height:48px;resize:vertical;font-size:13px;">${escHtml(scene?.setting || '')}</textarea>
      <div style="margin-top:8px;font-size:12px;color:var(--text-secondary);">
        出场人物：
        <span id="scene-char-tags" style="display:inline-flex;gap:4px;flex-wrap:wrap;align-items:center;"></span>
        <select id="add-char-select" style="font-size:11px;padding:1px 4px;border:1px dashed var(--border-color);border-radius:4px;background:transparent;max-width:140px;"></select>
      </div>
    </div>`;

    // 卡片列表（扁平索引，子元素也有独立索引）
    this.flattenElements();
    html += `<div id="card-list">`;
    for (let i = 0; i < this.elements.length; i++) {
      html += this.renderCard(this.elements[i], this.flatElements.indexOf(this.elements[i]), isMusical, 0);
    }
    html += `</div>`;

    // 底部添加按钮
    const types = [
      { type: 'action', label: '🎬 动作', icon: '🎬' },
      { type: 'dialogue', label: '💬 对白', icon: '💬' },
      { type: 'dual', label: '🗣 叠白', icon: '🗣' },
    ];
    if (isMusical) {
      types.push({ type: 'song', label: '🎵 歌曲', icon: '🎵' });
    }

    html += `<div style="margin-top:12px;text-align:center;">
      <span style="color:var(--text-muted);font-size:12px;">${Shortcuts.currentCombo('card.insert')} 插入 | 类型：</span>
      ${types.map((t, i) => `<button class="add-card-btn" data-type="${t.type}" style="margin:4px;padding:6px 14px;border:1px dashed var(--border-color);border-radius:6px;font-size:13px;cursor:pointer;">${t.label}</button>`).join('')}
    </div>`;

    wrap.innerHTML = html;

    // 聚焦选中卡片
    if (this.selectedCardIndex >= 0) {
      const cards = wrap.querySelectorAll('.script-card');
      if (cards[this.selectedCardIndex]) {
        cards[this.selectedCardIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
        const ta = cards[this.selectedCardIndex].querySelector('textarea');
        if (ta) setTimeout(() => ta.focus(), 200);
      }
    }

    this.bindEvents(wrap, isMusical, scene);
  },

  // 按卡片类型分发到 graph 渲染器注册表;六个类型的渲染器统一委托 _renderCardHtml(注册见文件末尾)
  renderCard(elem, index, isMusical, depth) {
    const graph = NW.plugins.graph;
    const renderer = graph && (graph.getRenderer(elem.element_type) || graph.getRenderer('action'));
    if (renderer) return renderer.render(this, elem, index, isMusical, depth);
    // 兜底:注册表不可用时走原实现(正常不会发生,script 依赖 graph,引导器按依赖序加载)
    return this._renderCardHtml(elem, index, isMusical, depth);
  },

  // 卡片渲染原实现:六种类型的差异(头部控件/角色选择/容器子元素)在本函数内按类型分支交错,
  // 拆不成六套独立渲染,故注册表的六个类型渲染器统一委托本函数
  _renderCardHtml(elem, index, isMusical, depth) {
    const selected = index === this.selectedCardIndex ? 'border-color:var(--accent);box-shadow:0 0 0 2px var(--accent);' : '';
    const typeConfig = {
      action: { icon: '🎬', label: '动作', bg: 'var(--bg-tertiary)', border: 'var(--border-color)' },
      dialogue: { icon: '💬', label: '对白', bg: 'var(--bg-primary)', border: 'var(--border-color)' },
      song: { icon: '🎵', label: '歌曲', bg: 'var(--card-song-bg)', border: 'var(--card-song-border)' },
      lyric: { icon: '🎤', label: '唱词', bg: 'var(--card-lyric-bg)', border: 'var(--card-lyric-border)' },
      ensemble: { icon: '🎼', label: '重唱', bg: 'var(--card-ensemble-bg)', border: 'var(--card-ensemble-border)' },
      dual: { icon: '🗣', label: '叠白', bg: 'var(--card-dual-bg)', border: 'var(--card-dual-border)' },
    };
    const cfg = typeConfig[elem.element_type] || typeConfig.action;
    const charName = (elem.element_type === 'lyric' || elem.element_type === 'dialogue')
      ? (elem.character_ids || []).map(id => this.characterList.find(c => c.id === id)?.name).filter(Boolean).join('、')
      : (elem.character_id ? (this.characterList.find(c => c.id === elem.character_id)?.name || '') : '');
    const isSongContainer = elem.element_type === 'song';
    const isEnsemble = elem.element_type === 'ensemble';
    const isDual = elem.element_type === 'dual';
    const isContainer = isSongContainer || isEnsemble || isDual;
    // 歌曲容器收起状态（仅 song 支持收起，ensemble/dual 不做）
    const songCollapsed = isSongContainer && !!((this.collapsedSongs || {})[elem.id]);
    const marginLeft = depth * 24;

    let html = '';
    html += `<div class="script-card" data-index="${index}" style="margin-bottom:8px;margin-left:${marginLeft}px;background:${cfg.bg};border:1px solid ${cfg.border};border-radius:8px;overflow:hidden;${selected}">`;

    // 卡片头部（歌曲头部标记 class/data-index，用于双击/右键切换收起）
    html += `<div ${isSongContainer ? `class="song-card-header" data-index="${index}" title="双击：收起/展开；右键：更多操作"` : ''} style="display:flex;align-items:center;padding:6px 10px;gap:8px;font-size:12px;border-bottom:1px solid var(--border-color);">`;

    // 歌曲折叠指示（收起时为 ▶，展开为 ▼）
    if (isSongContainer) {
      html += `<span class="song-collapse-toggle" style="user-select:none;font-size:11px;color:var(--text-muted);width:14px;flex:none;">${songCollapsed ? '▶' : '▼'}</span>`;
    }

    html += `<select class="card-type-select" data-index="${index}" style="border:none;background:transparent;font-size:12px;padding:2px;">
        <option value="action" ${elem.element_type==='action'?'selected':''}>🎬 动作</option>
        <option value="dialogue" ${elem.element_type==='dialogue'?'selected':''}>💬 对白</option>
        ${isMusical ? `<option value="song" ${elem.element_type==='song'?'selected':''}>🎵 歌曲</option>` : ''}
        ${isContainer || elem.element_type==='lyric' ? `<option value="lyric" ${elem.element_type==='lyric'?'selected':''}>🎤 唱词</option>` : ''}
        ${depth === 0 ? `<option value="dual" ${elem.element_type==='dual'?'selected':''}>🗣 叠白</option>` : ''}
      </select>`;

    // 角色选择：对白/动作单选下拉（对白可选多人齐白）；唱词多选按钮（合唱）
    if (elem.element_type === 'dialogue' || elem.element_type === 'action') {
      if (elem.element_type === 'dialogue' && (elem.character_ids || []).length > 1) {
        // 齐白：多个角色同说这句台词
        html += `<button class="card-chars-btn" data-index="${index}" title="齐白：多人同时说这句" style="border:1px dashed var(--border-color);background:transparent;font-size:12px;padding:2px 8px;border-radius:4px;cursor:pointer;">${escHtml(charName)}（齐） ▾</button>`;
      } else {
        html += `<select class="card-char-select" data-index="${index}" style="border:none;background:transparent;font-size:12px;min-width:80px;">
        <option value="">选择角色</option>
        ${this.characterList.map(c => `<option value="${c.id}" ${c.id===elem.character_id?'selected':''}>${escHtml(c.name)}</option>`).join('')}
        <option value="__new__" style="color:var(--accent);">+ 新建角色</option>
        ${elem.element_type === 'dialogue' ? '<option value="__multi__" style="color:var(--accent);">👥 齐白（多人同说）…</option>' : ''}
      </select>`;
      }
    } else if (elem.element_type === 'lyric') {
      html += `<button class="card-chars-btn" data-index="${index}" title="选择合唱角色" style="border:1px dashed var(--border-color);background:transparent;font-size:12px;padding:2px 8px;border-radius:4px;cursor:pointer;">${escHtml(charName) || '选择角色'} ▾</button>`;
    }

    // 歌曲标题（仅歌曲容器）
    if (isSongContainer) {
      html += `<input class="card-song-title" data-index="${index}" value="${escAttr(elem.song_title || '')}" placeholder="歌曲名" style="flex:1;border:none;background:transparent;font-size:13px;font-weight:bold;">`;
      // 收起时显示半透明子计数，作头部视觉区分
      if (songCollapsed) {
        html += `<span style="opacity:0.5;font-size:11px;white-space:nowrap;">${(elem.children || []).length} 项</span>`;
      }
      // 转为游离歌曲（仅顶层歌曲）
      if (depth === 0) {
        html += `<button class="card-to-floating" data-index="${index}" title="转为游离歌曲（移出正文，仅保留在 JSON 导出）" style="font-size:12px;padding:1px 4px;border:1px dashed var(--border-color);border-radius:4px;color:var(--text-secondary);">⇱ 游离</button>`;
      }
      // 乐谱（仅音乐剧顶层歌曲）：无乐谱时点击生成模板并调起 MuseScore
      if (depth === 0 && isMusical) {
        const hasScore = !!elem.score_file;
        html += `<button class="card-score-btn" data-index="${index}" title="${hasScore ? '用 MuseScore 编辑乐谱' : '创建乐谱并用 MuseScore 编辑'}" style="font-size:12px;padding:1px 4px;border:1px dashed ${hasScore ? 'var(--accent)' : 'var(--border-color)'};border-radius:4px;color:${hasScore ? 'var(--accent)' : 'var(--text-secondary)'};">🎼 乐谱${hasScore ? ' •' : ''}</button>`;
      }
    }
    // 重唱标识
    if (isEnsemble) {
      html += `<span style="font-size:13px;font-weight:bold;color:var(--ensemble-text);">🎼 重唱（多人同时唱不同的词）</span>`;
    }
    // 叠白标识
    if (isDual) {
      html += `<span style="font-size:13px;font-weight:bold;color:var(--dual-text);">🗣 叠白（多人同时说不同的话）</span>`;
    }

    html += `<span style="flex:1;"></span>`;
    html += `<button class="card-delete-btn" data-index="${index}" style="font-size:14px;padding:0 4px;color:var(--danger);opacity:0.5;" title="删除 (Delete)">×</button>`;
    html += `<span class="card-drag-handle" data-index="${index}" draggable="true" style="cursor:grab;font-size:14px;color:var(--text-muted);" title="拖拽排序">⋮⋮</span>`;
    html += `</div>`;

    // 卡片内容
    html += `<textarea class="card-content" data-index="${index}" placeholder="${cfg.label}内容..." style="width:100%;border:none;resize:vertical;min-height:${isContainer?'0':'48px'};padding:8px 10px;font-size:14px;line-height:1.6;background:transparent;display:${isContainer?'none':'block'};">${escHtml(elem.content || '')}</textarea>`;

    html += `</div>`;

    // 容器子元素（歌曲收起时不渲染子元素和容器内添加按钮）
    if (isContainer && elem.children && !songCollapsed) {
      for (let j = 0; j < elem.children.length; j++) {
        html += this.renderCard(elem.children[j], this.flatElements.indexOf(elem.children[j]), isMusical, depth + 1);
      }
      // 容器内添加按钮
      html += `<div style="margin-left:${(depth+1)*24}px;margin-bottom:8px;text-align:center;">`;
      if (isDual) {
        html += `<button class="add-song-child-btn" data-song-index="${index}" data-type="dialogue" style="margin:2px;padding:4px 10px;border:1px dashed var(--card-dual-border);border-radius:4px;font-size:11px;">+ 💬 对白</button>`;
      } else {
        html += `<button class="add-song-child-btn" data-song-index="${index}" data-type="lyric" style="margin:2px;padding:4px 10px;border:1px dashed var(--border-color);border-radius:4px;font-size:11px;">+ 🎤 唱词</button>`;
        if (isSongContainer) {
          html += `<button class="add-song-child-btn" data-song-index="${index}" data-type="dialogue" style="margin:2px;padding:4px 10px;border:1px dashed var(--border-color);border-radius:4px;font-size:11px;">+ 💬 歌中对白</button>`;
          html += `<button class="add-song-child-btn" data-song-index="${index}" data-type="ensemble" style="margin:2px;padding:4px 10px;border:1px dashed var(--card-ensemble-border);border-radius:4px;font-size:11px;">+ 🎼 重唱</button>`;
        }
      }
      html += `</div>`;
    }

    return html;
  },

  bindEvents(wrap, isMusical, scene) {
    // 场景信息保存
    wrap.querySelector('#scene-save-btn').onclick = async () => {
      const title = wrap.querySelector('#scene-title-input').value.trim();
      const setting = wrap.querySelector('#scene-setting-input').value;
      await api.scene.update(scene.id, { title, setting });
      toast('场景已保存');
      ScriptSidebar.refresh();
    };

    // 场景信息自动保存（失焦时）
    wrap.querySelector('#scene-title-input').addEventListener('blur', () => {
      wrap.querySelector('#scene-save-btn').click();
    });

    // 出场人物管理
    this.renderSceneCharacters(wrap, scene);
    wrap.querySelector('#add-char-select').addEventListener('change', async (ev) => {
      const sel = ev.target;
      const val = sel.value;
      if (!val) return;
      sel.value = '';
      const currentIds = (scene.characters || []).map(c => c.id);
      if (val === '__new__') {
        const name = await uiPrompt('新建角色名称:');
        if (!name) { this.renderSceneCharacters(wrap, scene); return; }
        const newChar = await api.character.create({ projectId: AppState.currentProject?.id, name });
        this.characterList.push(newChar);
        await api.scene.setCharacters(scene.id, [...currentIds, newChar.id]);
        if (!scene.characters) scene.characters = [];
        scene.characters.push(newChar);
        this.renderSceneCharacters(wrap, scene);
        return;
      }
      const cid = parseInt(val);
      await api.scene.setCharacters(scene.id, [...currentIds, cid]);
      const found = this.characterList.find(c => c.id === cid);
      if (found) {
        if (!scene.characters) scene.characters = [];
        scene.characters.push(found);
      }
      this.renderSceneCharacters(wrap, scene);
    });

    // 唱词合唱角色多选
    wrap.querySelectorAll('.card-chars-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const idx = parseInt(btn.dataset.index);
        const card = this.getCard(idx);
        if (!card) return;
        const options = this.characterList.map(c => ({ id: c.id, label: c.name }));
        const ids = await uiChecklist('选择合唱角色', options, card.character_ids || []);
        if (ids === null) return;
        card.character_ids = ids;
        card.character_id = ids[0] || null;
        await api.element.update(card.id, { characterIds: ids });
        this.render();
      });
    });

    // 类型切换
    wrap.querySelectorAll('.card-type-select').forEach(sel => {
      sel.addEventListener('change', async () => {
        const idx = parseInt(sel.dataset.index);
        const card = this.getCard(idx);
        if (card) {
          const newType = sel.value;
          card.element_type = newType;
          await api.element.update(card.id, { element_type: newType });
          this.render();
        }
      });
    });

    // 角色切换
    wrap.querySelectorAll('.card-char-select').forEach(sel => {
      sel.addEventListener('change', async () => {
        const idx = parseInt(sel.dataset.index);
        const card = this.getCard(idx);
        if (!card) return;
        if (sel.value === '__new__') {
          // 新建角色
          sel.value = ''; // reset
          const name = await uiPrompt('新建角色名称:');
          if (!name) { this.render(); return; }
          const projectId = AppState.currentProject?.id;
          const newChar = await api.character.create({ projectId, name });
          this.characterList.push(newChar);
          card.character_id = newChar.id;
          card.character_ids = [newChar.id];
          await api.element.update(card.id, { character_id: newChar.id, characterIds: [newChar.id] });
          this.render();
          return;
        }
        if (sel.value === '__multi__') {
          // 齐白：多选角色同说这句台词
          const options = this.characterList.map(c => ({ id: c.id, label: c.name }));
          const cur = (card.character_ids && card.character_ids.length) ? card.character_ids : (card.character_id ? [card.character_id] : []);
          const ids = await uiChecklist('齐白：选择同说这句台词的角色', options, cur);
          if (ids === null) { this.render(); return; }
          card.character_ids = ids;
          card.character_id = ids[0] || null;
          await api.element.update(card.id, { characterIds: ids });
          this.render();
          return;
        }
        // 单选：同步清掉齐白的多角色记录
        const cid = sel.value ? parseInt(sel.value) : null;
        card.character_id = cid;
        card.character_ids = cid ? [cid] : [];
        await api.element.update(card.id, { character_id: cid, characterIds: cid ? [cid] : [] });
      });
    });

    // 歌曲标题
    wrap.querySelectorAll('.card-song-title').forEach(inp => {
      inp.addEventListener('blur', async () => {
        const idx = parseInt(inp.dataset.index);
        const card = this.getCard(idx);
        if (card) {
          const title = inp.value.trim();
          card.song_title = title;
          await api.element.update(card.id, { song_title: title });
          // 歌名计入场总字数，保存后同步更新
          this.updateSceneWordCount();
        }
      });
    });

    // 歌曲转游离歌曲（逻辑见 convertSongToFloating，头部按钮与右键菜单共用）
    wrap.querySelectorAll('.card-to-floating').forEach(btn => {
      btn.addEventListener('click', () => {
        const card = this.getCard(parseInt(btn.dataset.index));
        if (card) this.convertSongToFloating(card);
      });
    });

    // 乐谱：创建/打开（MuseScore），成功后按钮原地高亮（不整树重绘，避免打断编辑）
    wrap.querySelectorAll('.card-score-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const card = this.getCard(parseInt(btn.dataset.index));
        if (!card) return;
        const ok = await ScoreHelper.openScore({ elementId: card.id, songTitle: card.song_title });
        if (ok) {
          card.score_file = card.score_file || '(pending)';
          btn.style.borderColor = 'var(--accent)';
          btn.style.color = 'var(--accent)';
          if (!btn.textContent.endsWith('•')) btn.textContent += ' •';
        }
      });
    });

    // 内容编辑（自动保存）；闭包捕获元素 id 而非索引，避免列表重建后写错卡片
    wrap.querySelectorAll('.card-content').forEach(ta => {
      const cardId = this.getCard(parseInt(ta.dataset.index))?.id;
      ta.addEventListener('blur', () => this.saveCardContent(ta, cardId));
      ta.addEventListener('input', debounce(() => this.saveCardContent(ta, cardId), 1000));
      ta.addEventListener('click', () => {
        const idx = parseInt(ta.dataset.index);
        this.selectedCardIndex = idx;
      });
    });

    // 删除（物理删除并级联删除子元素，先弹确认）
    wrap.querySelectorAll('.card-delete-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const idx = parseInt(btn.dataset.index);
        const elem = this.getCard(idx);
        if (elem) await this.deleteCard(elem);
      });
    });

    // 添加顶层卡片
    wrap.querySelectorAll('.add-card-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const type = btn.dataset.type;
        await api.element.create({ sceneId: this.currentSceneId, element_type: type });
        this.loadScene(this.currentSceneId);
      });
    });

    // 歌曲内添加子元素
    wrap.querySelectorAll('.add-song-child-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const songIdx = parseInt(btn.dataset.songIndex);
        const childType = btn.dataset.type;
        const song = this.getCard(songIdx);
        if (song) {
          await api.element.create({ sceneId: this.currentSceneId, parent_id: song.id, element_type: childType });
          this.loadScene(this.currentSceneId);
        }
      });
    });

    // 歌曲收起/展开：双击歌曲卡片头部直接切换；右键头部弹出菜单（收起/展开、转为游离歌曲）
    wrap.querySelectorAll('.song-card-header').forEach(header => {
      // 避开头部内的控件（歌名输入、类型/角色下拉、删除/游离按钮、拖拽手柄），控件上不触发
      const isOnControl = (ev) => !!ev.target.closest('input, select, button, textarea, .card-drag-handle');
      header.addEventListener('dblclick', (ev) => {
        if (isOnControl(ev)) return;
        ev.preventDefault();
        const card = this.getCard(parseInt(header.dataset.index));
        if (!card) return;
        // 纯前端状态，不触发保存/刷新
        this.toggleSongCollapsed(card.id);
        this.render();
      });
      header.addEventListener('contextmenu', (ev) => {
        if (isOnControl(ev)) return;
        ev.preventDefault();
        const card = this.getCard(parseInt(header.dataset.index));
        if (!card) return;
        this.showSongContextMenu(ev.clientX, ev.clientY, card);
      });
    });

    // 拖拽排序（同一层级内）
    let dragIdx = null;
    const clearIndicators = () => wrap.querySelectorAll('.script-card').forEach(c => {
      c.style.borderTop = ''; c.style.borderBottom = '';
    });
    wrap.querySelectorAll('.card-drag-handle').forEach(handle => {
      handle.addEventListener('dragstart', (e) => {
        dragIdx = parseInt(handle.dataset.index);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(dragIdx));
      });
      handle.addEventListener('dragend', () => { dragIdx = null; clearIndicators(); });
    });
    wrap.addEventListener('dragover', (e) => {
      if (dragIdx === null || !e.target.closest) return;
      const cardEl = e.target.closest('.script-card');
      if (!cardEl) return;
      e.preventDefault();
      clearIndicators();
      const rect = cardEl.getBoundingClientRect();
      const before = (e.clientY - rect.top) < rect.height / 2;
      cardEl.dataset.dropPos = before ? 'before' : 'after';
      if (before) cardEl.style.borderTop = '2px solid var(--accent)';
      else cardEl.style.borderBottom = '2px solid var(--accent)';
    });
    wrap.addEventListener('drop', async (e) => {
      if (dragIdx === null || !e.target.closest) return;
      const cardEl = e.target.closest('.script-card');
      clearIndicators();
      if (!cardEl) { dragIdx = null; return; }
      e.preventDefault();
      const targetIdx = parseInt(cardEl.dataset.index);
      const pos = cardEl.dataset.dropPos || 'after';
      const src = this.getCard(dragIdx);
      const tgt = this.getCard(targetIdx);
      dragIdx = null;
      if (!src || !tgt || src.id === tgt.id) return;
      const srcParent = src.parent_id || null;
      const tgtParent = tgt.parent_id || null;
      if (srcParent !== tgtParent) {
        toast('拖拽仅支持同一层级内排序（跨歌曲请用 Tab / Shift+Tab）', 'info');
        return;
      }
      let siblings;
      if (srcParent === null) {
        siblings = this.elements;
      } else {
        const parent = this.flatElements.find(el => el.id === srcParent);
        siblings = parent ? (parent.children || []) : [];
      }
      const ids = siblings.map(s => s.id).filter(id => id !== src.id);
      let insertAt = ids.indexOf(tgt.id);
      if (insertAt === -1) return;
      if (pos === 'after') insertAt += 1;
      ids.splice(insertAt, 0, src.id);
      await api.element.reorder(this.currentSceneId, srcParent, ids);
      this.loadScene(this.currentSceneId);
    });
  },

  // 按元素 id 查找并保存内容；元素已被删除或列表已重建时放弃保存
  async saveCardContent(ta, cardId) {
    const elem = this.flatElements.find(el => el.id === cardId);
    if (!elem) return;
    const content = ta.value;
    if (content !== elem.content) {
      elem.content = content;
      await api.element.update(elem.id, { content });
      // 保存成功后局部更新当前场字数（编辑区头部 + 侧栏该场节点）
      this.updateSceneWordCount();
    }
  },

  // 页面关闭/刷新前的兜底保存：对所有有改动的卡片发 keepalive 请求
  saveAllOnUnload() {
    if (!this.currentSceneId) return;
    document.querySelectorAll('#card-list .card-content').forEach(ta => {
      const cardId = this.getCard(parseInt(ta.dataset.index))?.id;
      const elem = this.flatElements.find(el => el.id === cardId);
      if (!elem || ta.value === elem.content) return;
      try {
        fetch(`/api/elements/${cardId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: ta.value }),
          keepalive: true,
        });
      } catch (e) { /* 页面正在卸载，忽略失败 */ }
    });
  },

  // 手动保存：立即保存当前场景所有卡片（冲刷各卡片的防抖自动保存）
  async saveAll() {
    if (!this.currentSceneId) return false;
    const tas = document.querySelectorAll('#card-list .card-content');
    for (const ta of tas) {
      const cardId = this.getCard(parseInt(ta.dataset.index))?.id;
      if (cardId) await this.saveCardContent(ta, cardId);
    }
    return true;
  },

  // 删除卡片：物理删除并级联删除全部子元素，不可恢复，必须确认
  async deleteCard(elem) {
    if (!await uiConfirm('确定删除此卡片吗？将同时删除其下所有子元素，且不可恢复。', { danger: true, okText: '删除' })) return;
    await api.element.delete(elem.id);
    toast('已删除');
    await this.loadScene(this.currentSceneId);
  },

  async renderSceneCharacters(wrap, scene) {
    const tagsDiv = wrap.querySelector('#scene-char-tags');
    const chars = scene.characters || [];
    const projectId = AppState.currentProject?.id;
    const allChars = await api.character.list(projectId);

    tagsDiv.innerHTML = chars.map(c => {
      const ch = allChars.find(ac => ac.id === c.id);
      return `<span style="background:var(--bg-active);border-radius:10px;padding:1px 8px;font-size:11px;display:inline-flex;align-items:center;gap:4px;">
        ${escHtml(ch?.name || c.name)}
        <span class="char-remove" data-cid="${c.id}" style="cursor:pointer;opacity:0.5;">×</span>
      </span>`;
    }).join('');

    tagsDiv.querySelectorAll('.char-remove').forEach(sp => {
      sp.addEventListener('click', async () => {
        const newIds = chars.filter(c => c.id !== parseInt(sp.dataset.cid)).map(c => c.id);
        await api.scene.setCharacters(scene.id, newIds);
        scene.characters = chars.filter(c => c.id !== parseInt(sp.dataset.cid));
        this.renderSceneCharacters(wrap, scene);
      });
    });

    // 填充“添加出场角色”下拉框（只列尚未出场的角色）
    const picker = wrap.querySelector('#add-char-select');
    if (picker) {
      const currentIds = chars.map(c => c.id);
      const available = allChars.filter(c => !currentIds.includes(c.id));
      picker.innerHTML = `<option value="">＋ 添加出场角色</option>` +
        available.map(c => `<option value="${c.id}">${escHtml(c.name)}</option>`).join('') +
        `<option value="__new__" style="color:var(--accent);">＋ 新建角色…</option>`;
    }
  },
};

// ====== graph 渲染器注册:剧本六种卡片类型 ======
// 各类型渲染差异在 _renderCardHtml 内部按类型分支交错(共享头部/尾部,差异在控件与子容器),
// 六个类型共用同一渲染实现;render 签名在注册表约定的 render(container, node) 之上
// 扩展为 render(editor, elem, index, isMusical, depth),由 CardEditor.renderCard 统一调用
const scriptCardRenderer = {
  render(editor, elem, index, isMusical, depth) {
    return editor._renderCardHtml(elem, index, isMusical, depth);
  },
};
for (const t of ['action', 'dialogue', 'song', 'lyric', 'ensemble', 'dual']) {
  NW.plugins.graph.registerRenderer(t, scriptCardRenderer);
}

// 迁移期兼容别名:未迁移组件(app.js/search-panel.js/floating-song-editor.js/score-helper.js 等)仍用全局名引用本组件
const CardEditor = NW.plugins.script.cardEditor;
window.CardEditor = CardEditor;

// ====== 快捷键（可自定义，见 Shortcuts；默认绑定保持不变） ======
document.addEventListener('keydown', (e) => {
  if (AppState.currentProject?.project_type === 'novel') return;

  const act = Shortcuts.actionFor(e);
  if (!act || !act.startsWith('card.')) return;

  const idx = CardEditor.selectedCardIndex;
  const elems = CardEditor.flatElements;
  const hasSelection = idx >= 0 && idx < elems.length;
  const tag = e.target.tagName || '';
  const isEditable = /^(INPUT|TEXTAREA|SELECT)$/.test(tag) || e.target.isContentEditable;
  const inCardArea = !!(e.target.closest && e.target.closest('#card-editor-wrap'));

  // 类型切换（编辑文本时不触发）
  const typeFor = {
    'card.typeAction': 'action',
    'card.typeDialogue': 'dialogue',
    'card.typeLyric': 'lyric',
    'card.typeSong': 'song',
  }[act];
  if (typeFor) {
    if (isEditable || !hasSelection) return;
    e.preventDefault();
    elems[idx].element_type = typeFor;
    api.element.update(elems[idx].id, { element_type: typeFor });
    CardEditor.render();
    return;
  }

  // 插入新卡片（随后按 1~4 选类型）
  if (act === 'card.insert') {
    if (!CardEditor.currentSceneId) return;
    e.preventDefault();
    const handler = async (ev) => {
      const typeMap = { '1': 'action', '2': 'dialogue', '3': 'lyric', '4': 'song' };
      if (typeMap[ev.key] && CardEditor.currentSceneId) {
        ev.preventDefault();
        await api.element.create({ sceneId: CardEditor.currentSceneId, element_type: typeMap[ev.key] });
        await CardEditor.loadScene(CardEditor.currentSceneId);
      }
      document.removeEventListener('keydown', handler);
    };
    document.addEventListener('keydown', handler, { once: true });
    return;
  }

  // 删除当前卡片（编辑文本时不触发；与 × 按钮一样走确认）
  if (act === 'card.delete') {
    if (isEditable || !hasSelection) return;
    e.preventDefault();
    CardEditor.deleteCard(elems[idx]);
    return;
  }

  // 快速切换角色（编辑文本时不触发）
  if (act === 'card.switchChar') {
    if (isEditable || !hasSelection) return;
    e.preventDefault();
    (async () => {
      const name = await uiPrompt('输入角色名（模糊匹配）:');
      if (name) {
        const found = CardEditor.characterList.find(c => c.name.includes(name));
        if (found) {
          elems[idx].character_id = found.id;
          api.element.update(elems[idx].id, { character_id: found.id });
          CardEditor.render();
        }
      }
    })();
    return;
  }

  // 移入 / 移出歌曲（焦点在卡片编辑区内才生效，避免抢走表单里的 Tab 焦点切换）
  if (act === 'card.indent' || act === 'card.outdent') {
    if (!inCardArea || !hasSelection) return;
    e.preventDefault();
    (async () => {
      if (act === 'card.outdent') {
        await api.element.move(elems[idx].id, null);
      } else {
        for (let i = idx - 1; i >= 0; i--) {
          if (elems[i].element_type === 'song') {
            await api.element.move(elems[idx].id, elems[i].id);
            break;
          }
        }
      }
      await CardEditor.loadScene(CardEditor.currentSceneId);
    })();
    return;
  }
});

// 生命周期事件:打开剧本/音乐剧项目时清空卡片编辑器(原由 app.js 点名调用)
NW.events.on('project.opened', ({ projectType } = {}) => {
  if (projectType === 'play' || projectType === 'musical') CardEditor.clear();
});
