package com.lulalulaluobo.wechatclipper

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class SessionStore(context: Context) {
    private val key = MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
    private val preferences = EncryptedSharedPreferences.create(
        context,
        "clipper-session",
        key,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    fun load(): Session? {
        val baseUrl = preferences.getString("base_url", null)
        val token = preferences.getString("token", null)
        return if (baseUrl.isNullOrBlank() || token.isNullOrBlank()) null else Session(baseUrl, token)
    }

    fun save(session: Session) {
        preferences.edit().putString("base_url", session.baseUrl).putString("token", session.token).apply()
    }

    fun clear() {
        preferences.edit().clear().apply()
    }
}
