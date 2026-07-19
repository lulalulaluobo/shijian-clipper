migrate((app) => {
  const settings = app.findCollectionByNameOrId("fns_settings")
  settings.fields.add(new TextField({ name: "attachment_dir" }))
  app.save(settings)
})
