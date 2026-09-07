"""内核实体注册表:插件声明「我有哪些数据实体」,供回收站/导出器等消费者按需查询

注册动作发生在各插件 activate() 时,消费者(回收站、json_transfer 等)在请求处理时
经 api.list_entities() 取用,无插件加载顺序依赖。内核只存元数据,不含业务逻辑。
设计见 docs/低耦合改造计划书.md D1 节。
"""
import threading

_lock = threading.Lock()
# (plugin_id, entity) -> 注册信息 dict
_entities = {}


def register_entity(plugin_id, entity, table, label, name_column="title",
                    export=False, export_order=100, fk=None, weak_fk=None,
                    recycle=True, export_hook=None, import_hook=None):
    """注册一个数据实体。同一 plugin_id+entity 重复注册抛错。

    - entity: 实体类型 id(回收站等接口里的类别字符串)
    - table: 表名
    - label: 显示名
    - name_column: 名称列(回收站列表展示用,默认 title)
    - export/export_order: 是否纳入 JSON 导出及导出/导入顺序(json_transfer 消费,
      外键依赖决定先后:被引用方的 export_order 必须更小)
    - fk: 强外键声明 {列名: 目标实体 entity}。导出时指向已排除行的行级联剔除;
      导入时按目标实体的 旧id→新id 映射重写,悬空(非 NULL 但映射不到)则整行跳过。
    - weak_fk: 弱外键声明 {列名: 目标实体 entity}。导出/导入时悬空引用置 NULL;
      目标为自身 entity 时是自引用(如 outlines.parent_id),导入先置 NULL 插入再统一回写。
    - recycle: 是否进回收站(附属表如 drafts/character_fields 无 deleted_at 列,置 False)
    - export_hook/import_hook: 默认处理器表达不了时的定制钩子(见 json_transfer 的调用约定),
      传了 hook 的实体跳过默认处理器
    """
    with _lock:
        key = (plugin_id, entity)
        if key in _entities:
            raise ValueError(f"插件 {plugin_id} 重复注册实体: {entity}")
        _entities[key] = {
            "plugin_id": plugin_id,
            "entity": entity,
            "table": table,
            "label": label,
            "name_column": name_column,
            "export": export,
            "export_order": export_order,
            "fk": dict(fk or {}),
            "weak_fk": dict(weak_fk or {}),
            "recycle": recycle,
            "export_hook": export_hook,
            "import_hook": import_hook,
        }


def list_entities():
    """全部注册信息的列表(拷贝,调用方可安全修改)"""
    with _lock:
        return [dict(info) for info in _entities.values()]


def _reset():
    """清空全部注册(供测试复用)"""
    with _lock:
        _entities.clear()
