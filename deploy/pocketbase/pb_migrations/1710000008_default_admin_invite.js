migrate((app) => {
  try {
    const collection = app.findCollectionByNameOrId("invite_codes")
    const record = new Record(collection)
    // ec856256fd351acbe3e5cdd377247da5417d472dbbd2067021ee0eaa57a67aa1 是 "shijian_admin" 的 SHA-256 哈希值
    record.set("code_hash", "ec856256fd351acbe3e5cdd377247da5417d472dbbd2067021ee0eaa57a67aa1")
    app.save(record)
  } catch (err) {
    console.log("Failed to insert default admin invite code: " + err)
  }
}, (app) => {
  try {
    const record = app.findFirstRecordByFilter(
      "invite_codes",
      "code_hash = 'ec856256fd351acbe3e5cdd377247da5417d472dbbd2067021ee0eaa57a67aa1'"
    )
    if (record) {
      app.delete(record)
    }
  } catch (_) {}
})
