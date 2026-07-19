package com.lulalulaluobo.wechatclipper

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class Session(val baseUrl: String, val token: String)
data class FnsSettings(val configured: Boolean, val baseUrl: String, val vault: String, val targetDir: String)
data class FnsCheck(val vaultExists: Boolean, val vaultChecked: Boolean)
data class ClipTask(val id: String, val sourceUrl: String, val status: String, val title: String, val errorMessage: String)

class ApiException(override val message: String) : Exception(message)

class ApiClient(private val baseUrl: String, private val token: String? = null) {
    fun register(inviteCode: String, email: String, password: String) {
        request("POST", "/v1/auth/register", JSONObject().put("invite_code", inviteCode).put("email", email).put("password", password))
    }

    fun login(email: String, password: String): Session {
        val response = request("POST", "/v1/auth/login", JSONObject().put("email", email).put("password", password))
        return Session(baseUrl, response.requiredString("token"))
    }

    fun getFnsSettings(): FnsSettings {
        val response = request("GET", "/v1/settings/fns")
        return FnsSettings(
            configured = response.optBoolean("configured"),
            baseUrl = response.optString("base_url"),
            vault = response.optString("vault"),
            targetDir = response.optString("target_dir"),
        )
    }

    fun saveFnsSettings(config: String, targetDir: String): FnsSettings {
        val response = request("PUT", "/v1/settings/fns", JSONObject().put("config", config).put("target_dir", targetDir))
        return FnsSettings(true, response.optString("base_url"), response.optString("vault"), response.optString("target_dir"))
    }

    fun checkFnsSettings(): FnsCheck {
        val response = request("POST", "/v1/settings/fns/check")
        return FnsCheck(response.optBoolean("vault_exists"), response.optBoolean("vault_checked", true))
    }

    fun canCreateInvites(): Boolean = request("GET", "/v1/invites").optBoolean("can_create")

    fun createInvite(): String = request("POST", "/v1/invites").requiredString("code")

    fun createClip(url: String): ClipTask = taskFrom(request("POST", "/v1/clips", JSONObject().put("url", url)))

    fun listClips(): List<ClipTask> {
        val items = request("GET", "/v1/clips").optJSONArray("items") ?: JSONArray()
        return List(items.length()) { taskFrom(items.getJSONObject(it)) }
    }

    fun retryClip(taskId: String): ClipTask = taskFrom(request("POST", "/v1/clips/$taskId/retry"))

    private fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        val connection = (URL(baseUrl + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 30_000
            readTimeout = 30_000
            setRequestProperty("Accept", "application/json")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.bufferedWriter().use { it.write(body.toString()) }
            }
        }
        return try {
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val payload = JSONObject(text.ifBlank { "{}" })
            if (connection.responseCode !in 200..299) throw ApiException(payload.optString("message", "服务请求失败"))
            payload
        } catch (error: ApiException) {
            throw error
        } catch (_: Exception) {
            throw ApiException("请求失败，请检查网络和服务地址。")
        } finally {
            connection.disconnect()
        }
    }

    private fun taskFrom(value: JSONObject): ClipTask = ClipTask(
        id = value.requiredString("id"),
        sourceUrl = value.optString("source_url"),
        status = value.requiredString("status"),
        title = value.optString("title"),
        errorMessage = value.optString("error_message"),
    )
}

private fun JSONObject.requiredString(name: String): String = optString(name).takeIf { it.isNotBlank() }
    ?: throw ApiException("服务响应无效")
