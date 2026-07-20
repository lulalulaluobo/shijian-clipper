migrate((app) => {
  try {
    const collection = app.findCollectionByNameOrId("invite_codes")
    const record = new Record(collection)
    // 33d13042a01d39b2b91d47739d5e7023dc32c12546a01a3426014585bb830c8a 是 "shijian_first" 的 SHA-256 哈希值
    record.set("code_hash", "33d13042a01d39b2b91d47739d5e7023dc32c12546a01a3426014585bb830c8a")
    app.save(record)
  } catch (err) {
    console.log("Failed to insert default admin invite code: " + err)
  }
}, (app) => {
  try {
    const record = app.findFirstRecordByFilter(
      "invite_codes",
      "code_hash = '33d13042a01d39b2b91d47739d5e7023dc32c12546a01a3426014585bb830c8a'"
    )
    if (record) {
      app.delete(record)
    }
  } catch (_) {}
})
