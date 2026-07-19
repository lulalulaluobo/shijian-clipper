migrate((app) => {
  const users = app.findCollectionByNameOrId("users")
  users.fields.add(new DateField({ name: "access_expires_at" }))
  app.save(users)

  const invites = app.findCollectionByNameOrId("invite_codes")
  invites.fields.add(new TextField({ name: "code" }))
  app.save(invites)

  app.db().newQuery("UPDATE users SET access_expires_at = datetime(created, '+30 days') WHERE access_expires_at = ''").execute()
})
