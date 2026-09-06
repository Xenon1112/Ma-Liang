// ====== 内核 JS:插件挂载点与扩展点注册表 ======
// 依赖 state.js(事件总线),须在 state.js 之后、其余组件之前加载

window.NW = {
  plugins: {},          // 插件挂载点:NW.plugins.inspiration = {...}
  events: AppState,     // 现有事件总线,原样保留
  pluginRegistry: null, // /api/plugins/registry 返回的清单(由 index.html 引导脚本填充)
  pluginsReady: null,   // Promise:插件前端脚本全部加载完后 resolve(由引导脚本填充)

  _ext: {},             // 扩展点注册表:extPoint -> [component, ...]

  registerComponent(extPoint, component) {
    if (!this._ext[extPoint]) this._ext[extPoint] = [];
    this._ext[extPoint].push(component);
  },

  getComponents(extPoint) {
    return this._ext[extPoint] || [];
  },
};
