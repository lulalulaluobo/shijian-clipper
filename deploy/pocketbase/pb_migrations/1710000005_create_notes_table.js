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
      { name: "content_md", type: "text" },
      { name: "images", type: "json" },
      { name: "kind", type: "select", required: true, maxSelect: 1, values: ["article", "attachment"] },
      { name: "attachment_filename", type: "text" },
      { name: "attachment_mime", type: "text" },
      { name: "attachment_b64", type: "text" },
      { name: "delivered", type: "bool", required: true },
      { name: "delivered_at", type: "date" },
      { name: "error_stage", type: "text" },
      { name: "error_message", type: "text" },
    ],
    indexes: [
      "CREATE INDEX idx_notes_user_delivered ON notes (user, delivered, created)",
      "CREATE INDEX idx_notes_created ON notes (created)",
    ],
  })
  app.save(notes)
}, (app) => {
  app.delete(app.findCollectionByNameOrId("notes"))
})
