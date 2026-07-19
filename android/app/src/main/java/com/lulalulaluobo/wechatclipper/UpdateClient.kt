package com.lulalulaluobo.wechatclipper

import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

private const val GITHUB_RELEASE_API = "https://api.github.com/repos/lulalulaluobo/shijian-clipper/releases/latest"
private const val GITHUB_RELEASE_PREFIX = "https://github.com/lulalulaluobo/shijian-clipper/releases/download/"
private const val MAX_RELEASE_METADATA_BYTES = 128 * 1024
private const val MAX_APK_BYTES = 100L * 1024 * 1024
private val releaseTagPattern = Regex("^v(\\d+\\.\\d+\\.\\d+)$")
private val releaseAssetPattern = Regex("^Shijian-v(\\d+\\.\\d+\\.\\d+)-(\\d+)-release\\.apk$")
private val sha256DigestPattern = Regex("^sha256:([0-9a-f]{64})$", RegexOption.IGNORE_CASE)

data class ReleaseUpdate(
    val versionName: String,
    val versionCode: Int,
    val assetName: String,
    val downloadUrl: String,
    val sha256: String,
)

class UpdateException(override val message: String) : Exception(message)

fun parseReleaseUpdate(payload: String, currentVersionCode: Int): ReleaseUpdate? {
    val release = JSONObject(payload)
    val tagName = release.optString("tag_name")
    val versionName = releaseTagPattern.matchEntire(tagName)?.groupValues?.get(1) ?: return null
    val assets = release.optJSONArray("assets") ?: return null

    for (index in 0 until assets.length()) {
        val asset = assets.optJSONObject(index) ?: continue
        val assetName = asset.optString("name")
        val assetMatch = releaseAssetPattern.matchEntire(assetName) ?: continue
        if (assetMatch.groupValues[1] != versionName) continue
        val versionCode = assetMatch.groupValues[2].toIntOrNull() ?: continue
        if (versionCode <= currentVersionCode) return null
        val downloadUrl = asset.optString("browser_download_url")
        val expectedUrl = "$GITHUB_RELEASE_PREFIX$tagName/$assetName"
        if (downloadUrl != expectedUrl) continue
        val sha256 = sha256DigestPattern.matchEntire(asset.optString("digest"))?.groupValues?.get(1) ?: continue
        return ReleaseUpdate(versionName, versionCode, assetName, downloadUrl, sha256.lowercase())
    }
    return null
}

object UpdateClient {
    fun checkForUpdate(currentVersionCode: Int): ReleaseUpdate? {
        val connection = openConnection(GITHUB_RELEASE_API)
        return try {
            connection.setRequestProperty("Accept", "application/vnd.github+json")
            val response = connection.responseCode
            if (response !in 200..299) throw UpdateException("无法检查更新，请稍后重试。")
            val payload = connection.inputStream.use { it.readLimitedText(MAX_RELEASE_METADATA_BYTES) }
            parseReleaseUpdate(payload, currentVersionCode)
        } catch (error: UpdateException) {
            throw error
        } catch (_: Exception) {
            throw UpdateException("无法检查更新，请检查网络后重试。")
        } finally {
            connection.disconnect()
        }
    }

    fun downloadAndVerify(context: Context, update: ReleaseUpdate): File {
        val expectedUrl = "${GITHUB_RELEASE_PREFIX}v${update.versionName}/${update.assetName}"
        require(update.downloadUrl == expectedUrl) { "更新地址无效。" }
        val updatesDirectory = File(context.cacheDir, "updates")
        if (!updatesDirectory.exists() && !updatesDirectory.mkdirs()) throw UpdateException("无法创建更新文件。")
        val temporaryFile = File(updatesDirectory, "${update.assetName}.part")
        val apkFile = File(updatesDirectory, update.assetName)
        val connection = openConnection(update.downloadUrl).apply { instanceFollowRedirects = true }

        try {
            val response = connection.responseCode
            if (response !in 200..299) throw UpdateException("下载更新失败，请稍后重试。")
            if (connection.contentLengthLong > MAX_APK_BYTES) throw UpdateException("更新文件过大，已取消下载。")

            val digest = MessageDigest.getInstance("SHA-256")
            var downloaded = 0L
            connection.inputStream.use { input ->
                FileOutputStream(temporaryFile).use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        downloaded += count
                        if (downloaded > MAX_APK_BYTES) throw UpdateException("更新文件过大，已取消下载。")
                        digest.update(buffer, 0, count)
                        output.write(buffer, 0, count)
                    }
                }
            }
            if (digest.digest().toHex() != update.sha256) throw UpdateException("更新文件校验失败，已取消安装。")
            if (apkFile.exists() && !apkFile.delete()) throw UpdateException("无法替换旧更新文件。")
            if (!temporaryFile.renameTo(apkFile)) throw UpdateException("无法准备更新文件。")
            verifyArchive(context, apkFile, update)
            return apkFile
        } catch (error: UpdateException) {
            temporaryFile.delete()
            throw error
        } catch (_: Exception) {
            temporaryFile.delete()
            throw UpdateException("下载或校验更新失败，请稍后重试。")
        } finally {
            connection.disconnect()
        }
    }

    fun canRequestInstalls(context: Context): Boolean = context.packageManager.canRequestPackageInstalls()

    fun openInstallPermissionSettings(context: Context) {
        context.startActivity(
            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    fun requestUserConfirmedInstall(context: Context, apkFile: File) {
        val apkUri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", apkFile)
        context.startActivity(
            Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(apkUri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            },
        )
    }

    private fun verifyArchive(context: Context, apkFile: File, update: ReleaseUpdate) {
        @Suppress("DEPRECATION")
        val archive = context.packageManager.getPackageArchiveInfo(apkFile.absolutePath, PackageManager.GET_SIGNING_CERTIFICATES)
            ?: throw UpdateException("更新文件不是有效的 APK。")
        if (archive.packageName != context.packageName) throw UpdateException("更新包名不匹配，已取消安装。")
        @Suppress("DEPRECATION")
        val archiveVersionCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) archive.longVersionCode else archive.versionCode.toLong()
        if (archiveVersionCode != update.versionCode.toLong()) throw UpdateException("更新版本不匹配，已取消安装。")

        @Suppress("DEPRECATION")
        val installed = context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
        val archiveSignatures = signingCertificateHashes(archive)
        if (archiveSignatures.isEmpty() || archiveSignatures != signingCertificateHashes(installed)) {
            throw UpdateException("更新签名与当前应用不一致，已取消安装。")
        }
    }

    @Suppress("DEPRECATION")
    private fun signingCertificateHashes(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info.signingInfo?.apkContentsSigners
        } else {
            info.signatures
        } ?: return emptySet()
        return signatures.map { signature ->
            MessageDigest.getInstance("SHA-256").digest(signature.toByteArray()).toHex()
        }.toSet()
    }

    private fun openConnection(url: String): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 15_000
        readTimeout = 45_000
        instanceFollowRedirects = false
    }
}

private fun java.io.InputStream.readLimitedText(maxBytes: Int): String {
    val output = StringBuilder()
    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
    var total = 0
    while (true) {
        val count = read(buffer)
        if (count < 0) break
        total += count
        if (total > maxBytes) throw UpdateException("更新信息过大，已取消检查。")
        output.append(buffer.decodeToString(0, count))
    }
    return output.toString()
}

private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
