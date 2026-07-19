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

    fun loadServerUrl(): String = preferences.getString("base_url", DEFAULT_SERVER_URL).orEmpty().ifBlank { DEFAULT_SERVER_URL }

    fun save(session: Session) {
        preferences.edit().putString("base_url", session.baseUrl).putString("token", session.token).apply()
    }

    fun saveServerUrl(serverUrl: String) {
        preferences.edit().putString("base_url", serverUrl).apply()
    }

    fun clear() {
        preferences.edit().remove("token").apply()
    }
}
