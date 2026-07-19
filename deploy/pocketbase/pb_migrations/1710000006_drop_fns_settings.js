migrate((app) => {
  const collection = app.findCollectionByNameOrId("fns_settings")
  app.delete(collection)
}, (app) => {
  // 回滚：按 initial.js 的定义重建 fns_settings collection
  const users = app.findCollectionByNameOrId("users")
  const settings = new Collection({
    id: "fnsset000000001",
    type: "base",
    name: "fns_settings",
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
    fields: [
      { name: "user", type: "relation", required: true, collectionId: users.id, maxSelect: 1, cascadeDelete: true },
      { name: "base_url", type: "url", required: true },
      { name: "vault", type: "text", required: true },
      { name: "target_dir", type: "text", required: true },
      { name: "token_ciphertext", type: "text", required: true, hidden: true },
      { name: "attachment_dir", type: "text" },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_fns_settings_user ON fns_settings (user)"],
  })
  app.save(settings)
})
