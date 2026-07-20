migrate((app) => {
  const users = app.findCollectionByNameOrId("users")

  const notes = new Collection({
    id: "notes00000000001",
    type: "base",
    name: "notes",
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
    fields: [
      { name: "user", type: "relation", required: true, collectionId: users.id, maxSelect: 1, cascadeDelete: true },
      { name: "source_url", type: "url", required: true },
      { name: "title", type: "text", required: true },
      { name: "filename", type: "text", required: true },
      { name: "content_md", type: "text", max: 10000000 },
      { name: "images", type: "json" },
      { name: "kind", type: "select", required: true, maxSelect: 1, values: ["article", "attachment"] },
      { name: "attachment_filename", type: "text" },
      { name: "attachment_mime", type: "text" },
      { name: "attachment_b64", type: "text", max: 30000000 },
      // 注意：PocketBase 0.38 的 bool 字段在 list filter 里解析失败（已知问题），
      // 故 delivered 用 number 字段（0=未交付，1=已交付）。
      { name: "delivered", type: "number" },
      { name: "delivered_at", type: "date" },
      { name: "error_stage", type: "text" },
      { name: "error_message", type: "text" },
    ],
    // 不在此声明索引：PocketBase collection 创建阶段无法引用 created 自动字段，
    // 且 MVP 阶段数据量小，索引收益有限（ponytail 原则）。
    // 数据量增长后可新增 migration 用 raw SQL 添加 (user, delivered, created) 索引。
  })
  app.save(notes)
}, (app) => {
  app.delete(app.findCollectionByNameOrId("notes"))
})
