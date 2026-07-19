migrate((app) => {
  const users = app.findCollectionByNameOrId("users")

  const inviteCodes = new Collection({
    id: "invite000000001",
    type: "base",
    name: "invite_codes",
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
    fields: [
      { name: "code_hash", type: "text", required: true, max: 64 },
      { name: "used_by", type: "relation", collectionId: users.id, maxSelect: 1 },
      { name: "used_at", type: "date" },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_invite_code_hash ON invite_codes (code_hash)"],
  })
  app.save(inviteCodes)

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
    ],
    indexes: ["CREATE UNIQUE INDEX idx_fns_settings_user ON fns_settings (user)"],
  })
  app.save(settings)

  const tasks = new Collection({
    id: "cliptask0000001",
    type: "base",
    name: "clip_tasks",
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
    fields: [
      { name: "user", type: "relation", required: true, collectionId: users.id, maxSelect: 1, cascadeDelete: true },
      { name: "source_url", type: "url", required: true },
      { name: "status", type: "select", required: true, maxSelect: 1, values: ["queued", "processing", "succeeded", "failed"] },
      { name: "title", type: "text" }, { name: "path", type: "text" },
      { name: "error_stage", type: "text" }, { name: "error_message", type: "text" },
    ],
  })
  app.save(tasks)

  const superusers = app.findCollectionByNameOrId("_superusers")
  const admin = new Record(superusers)
  admin.set("email", $os.getenv("POCKETBASE_ADMIN_EMAIL"))
  admin.set("password", $os.getenv("POCKETBASE_ADMIN_PASSWORD"))
  app.save(admin)
}, (app) => {
  ;["clip_tasks", "fns_settings", "invite_codes"].forEach((name) => app.delete(app.findCollectionByNameOrId(name)))
})
