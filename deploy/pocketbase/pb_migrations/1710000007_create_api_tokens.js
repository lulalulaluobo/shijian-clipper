migrate((app) => {
  const users = app.findCollectionByNameOrId("users")

  const apiTokens = new Collection({
    id: "apitoken000001",
    type: "base",
    name: "api_tokens",
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
    fields: [
      { name: "user", type: "relation", required: true, collectionId: users.id, maxSelect: 1, cascadeDelete: true },
      { name: "token_hash", type: "text", required: true, max: 64 },
      { name: "label", type: "text", max: 128 },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_api_token_hash ON api_tokens (token_hash)"],
  })
  app.save(apiTokens)
}, (app) => {
  app.delete(app.findCollectionByNameOrId("api_tokens"))
})
