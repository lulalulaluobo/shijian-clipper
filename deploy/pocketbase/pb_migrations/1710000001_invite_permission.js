migrate((app) => {
  const users = app.findCollectionByNameOrId("users")
  users.fields.add(new BoolField({ name: "can_create_invites" }))
  app.save(users)
})
