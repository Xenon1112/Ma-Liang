// ====== 编辑器 ======

const Editor = {
  currentDraftId: null,
  saveTimer: null,

  async loadChapter(chapterId) {
    const chapter = await api.chapter.get(chapterId);
    if (!chapter) return;

    const draft = await api.draft.getCurrent(chapterId, null);
    const textarea = document.getElementById('editor');
    textarea.value = draft ? draft.content : '';
    textarea.disabled = false;
    textarea.focus();

    this.currentDraftId = draft?.id || null;
    AppState.setDirty(false);

    document.getElementById('breadcrumb-ch').textContent = chapter.title;
    document.getElementById('breadcrumb-vol').textContent = AppState.currentVolume?.title || '';
    Editor.updateWordCount();

    // 加载版本历史
    VersionPanel.refresh(chapterId, null);
  },

  async loadVolumePreface(volume) {
    const draft = await api.draft.getCurrent(null, volume.id);
    const textarea = document.getElementById('editor');
    textarea.value = draft ? draft.content : volume.preface || '';
    textarea.disabled = false;

    this.currentDraftId = draft?.id || null;
    AppState.setDirty(false);

    document.getElementById('breadcrumb-ch').textContent = '卷首语';
    document.getElementById('breadcrumb-vol').textContent = volume.title;
    Editor.updateWordCount();

    VersionPanel.refresh(null, volume.id);
  },

  scheduleSave() {
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.save(), 2000);
  },

  async save() {
    const chId = AppState.currentChapter?.id;
    const volId = AppState.currentVolume?.id;
    const isPreface = !chId && volId;

    if (!chId && !isPreface) return;

    try {
      const content = document.getElementById('editor').value;
      const result = await api.draft.save({
        chapterId: chId || undefined,
        volumeId: isPreface ? volId : undefined,
        content,
        versionTag: 'auto',
      });

      this.currentDraftId = result.id;
      AppState.setDirty(false);
      Editor.updateWordCount();

      // 刷新侧栏字数
      Sidebar.refresh();
      VersionPanel.refresh(chId, isPreface ? volId : null);
    } catch (err) {
      console.error('Save failed:', err);
      toast('保存失败: ' + err.message, 'error');
    }
  },

  updateWordCount() {
    const text = document.getElementById('editor').value;
    const { chinese, total } = countWords(text);
    document.getElementById('word-count-chinese').textContent = chinese;
    document.getElementById('word-count-total').textContent = total;
  },

  // 清空编辑器
  clear() {
    const textarea = document.getElementById('editor');
    textarea.value = '';
    textarea.disabled = true;
    textarea.placeholder = '选择左侧目录树中的章节开始写作...';
    document.getElementById('breadcrumb-ch').textContent = '选择章';
    document.getElementById('breadcrumb-vol').textContent = '选择卷';
    document.getElementById('word-count-chinese').textContent = '0';
    document.getElementById('word-count-total').textContent = '0';
    this.currentDraftId = null;
  },
};

// ====== Editor 事件 ======
document.addEventListener('DOMContentLoaded', () => {
  const textarea = document.getElementById('editor');

  textarea.addEventListener('input', () => {
    AppState.setDirty(true);
    Editor.updateWordCount();
    Editor.scheduleSave();
  });

  // Ctrl+S 手动保存
  textarea.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      Editor.save();
      toast('已保存');
    }
  });

  // 初始禁用
  textarea.disabled = true;
});
