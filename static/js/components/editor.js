// ====== 编辑器 ======

const Editor = {
  currentDraftId: null,
  saveTimer: null,
  saveSnapshot: null, // scheduleSave 时捕获的保存目标 {chapterId, volumeId}

  async loadChapter(chapterId) {
    // 切换前冲刷待触发的自动保存：按快照对旧章节立即保存（此时编辑器还是旧内容）
    await this.flushSave();

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
    // 切换前冲刷待触发的自动保存（同上）
    await this.flushSave();

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
    // 捕获保存目标快照：定时器触发时若章节已切换，仍按快照保存，防止写到新章
    this.saveSnapshot = {
      chapterId: AppState.currentChapter?.id || null,
      volumeId: AppState.currentChapter ? null : (AppState.currentVolume?.id || null),
    };
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.save();
    }, 2000);
  },

  // 立即执行待触发的自动保存（切换章节/卷首语前调用）
  async flushSave() {
    if (!this.saveTimer) return;
    clearTimeout(this.saveTimer);
    this.saveTimer = null;
    await this.save();
  },

  async save() {
    // 优先按快照目标保存；无快照（手动保存等）则按当前章节
    const snap = this.saveSnapshot;
    this.saveSnapshot = null;
    const chId = snap ? snap.chapterId : AppState.currentChapter?.id;
    const volId = snap ? snap.volumeId : (chId ? null : AppState.currentVolume?.id);
    const isPreface = !chId && volId;

    if (!chId && !isPreface) return false;

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
      return true;
    } catch (err) {
      console.error('Save failed:', err);
      toast('保存失败: ' + err.message, 'error');
      return false;
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
    // 取消待触发的自动保存，防止写入已切换/已删除的章节
    clearTimeout(this.saveTimer);
    this.saveTimer = null;
    this.saveSnapshot = null;
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

  // Ctrl+S 手动保存（成功后再提示，避免与"保存失败"提示矛盾）
  textarea.addEventListener('keydown', async (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      if (await Editor.save()) toast('已保存');
    }
  });

  // 初始禁用
  textarea.disabled = true;
});
