"""km_counter:插件协议总验收测试插件(tests/fixtures 下的第三方形态 fixture)

按协议标准形态实现,不使用 legacy_routes 逃生门,覆盖协议表面对象:
- register_entity:声明带 fk 的数据实体(进回收站 + 纳入 JSON 导出);
- api.route:仅注册 /api/plugins/km_counter/ 前缀路由;
- migrations/001_init.sql 建表;
- web/km-counter.js 注册扩展点并订阅前端事件。

符合性验证见 tests/run_conformance.py,本目录不被正式应用扫描(不在 plugins/ 下)。
"""


class Plugin:
    def activate(self, api):
        # 实体声明:fk 指向 project 实体,json_transfer 默认处理器按此做导出级联与导入重映射
        api.register_entity(
            entity="km_note",
            table="km_counter__notes",
            label="计数笔记",
            name_column="name",
            export=True,
            export_order=90,
            fk={"project_id": "project"},
        )

        @api.route("/api/plugins/km_counter/notes", methods=["GET"])
        def list_notes():
            conn = api.db()
            try:
                rows = [api.row_to_dict(r) for r in conn.execute(
                    "SELECT * FROM km_counter__notes ORDER BY id")]
            finally:
                conn.close()
            return api.jsonify(rows)
