// ====== graph 插件前端:块级节点渲染器注册表 ======
// 地基本期只立机制:各节点类型的渲染器由消费方插件注册
// (形状 {render(container, node), ...}),暂无实际渲染消费方。
// graph 无 UI 面板,不注册 sidebar.tabs / toolbar.actions 扩展点。

NW.plugins.graph = {
  _renderers: {},

  // 注册某节点类型的渲染器;renderer 必须含 render(container, node),重复注册抛错
  registerRenderer(type, renderer) {
    if (this._renderers[type]) {
      throw new Error(`graph 渲染器重复注册: ${type}`);
    }
    if (!renderer || typeof renderer.render !== 'function') {
      throw new Error(`graph 渲染器缺少 render(container, node): ${type}`);
    }
    this._renderers[type] = renderer;
  },

  // 取某节点类型的渲染器,未注册返回 null
  getRenderer(type) {
    return this._renderers[type] || null;
  },
};
