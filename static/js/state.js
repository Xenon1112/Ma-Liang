const AppState = {
  currentView: 'project-list', // 'project-list' | 'workspace'
  currentProject: null,
  currentVolume: null,
  currentChapter: null,
  isDirty: false,
  isFocusMode: false,
  theme: 'light',
  rightPanelTab: 'outline', // 'outline' | 'character' | 'world' | 'inspiration'
  config: {},

  setView(view) {
    this.currentView = view;
    this.emit('viewChange', view);
  },

  setProject(project) {
    this.currentProject = project;
    this.currentVolume = null;
    this.currentChapter = null;
    this.emit('projectChange', project);
  },

  setVolume(volume) {
    this.currentVolume = volume;
    this.emit('volumeChange', volume);
  },

  setChapter(chapter) {
    this.currentChapter = chapter;
    this.emit('chapterChange', chapter);
  },

  setDirty(dirty) {
    this.isDirty = dirty;
    this.emit('dirtyChange', dirty);
  },

  setFocusMode(focus) {
    this.isFocusMode = focus;
    this.emit('focusChange', focus);
  },

  setTheme(theme) {
    this.theme = theme;
    document.body.className = `theme-${theme}`;
    this.emit('themeChange', theme);
  },

  // Simple event system
  _listeners: {},

  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  },

  emit(event, data) {
    (this._listeners[event] || []).forEach(fn => fn(data));
  },
};
