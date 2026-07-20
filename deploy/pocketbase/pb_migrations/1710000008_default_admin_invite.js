migrate((app) => {
  try {
    const collection = app.findCollectionByNameOrId("invite_codes")
    const record = new Record(collection)
    // f48a205182ce86213f0ff002dd71b299c4205d0997784e42bdbe07c082bcc64e 是 "shijian_amin" 的 SHA-256 哈希值
    record.set("code_hash", "f48a205182ce86213f0ff002dd71b299c4205d0997784e42bdbe07c082bcc64e")
    app.save(record)
  } catch (err) {
    console.log("Failed to insert default admin invite code: " + err)
  }
}, (app) => {
  try {
    const record = app.findFirstRecordByFilter(
      "invite_codes",
      "code_hash = 'f48a205182ce86213f0ff002dd71b299c4205d0997784e42bdbe07c082bcc64e'"
    )
    if (record) {
      app.delete(record)
    }
  } catch (_) {}
})
