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
                    export=False, export_order=100):
    """注册一个数据实体。同一 plugin_id+entity 重复注册抛错。

    - entity: 实体类型 id(回收站等接口里的类别字符串)
    - table: 表名
    - label: 显示名
    - name_column: 名称列(回收站列表展示用,默认 title)
    - export/export_order: 是否纳入 JSON 导出及导出顺序(步骤 2 json_transfer 消费,本期先存着)
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
        }


def list_entities():
    """全部注册信息的列表(拷贝,调用方可安全修改)"""
    with _lock:
        return [dict(info) for info in _entities.values()]


def _reset():
    """清空全部注册(供测试复用)"""
    with _lock:
        _entities.clear()
