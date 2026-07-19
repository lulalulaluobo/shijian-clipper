migrate((app) => {
  const collection = app.findCollectionByNameOrId("invite_codes")
  collection.fields.removeByName("used_by")
  collection.fields.add(new TextField({ name: "used_by" }))
  app.save(collection)
})
