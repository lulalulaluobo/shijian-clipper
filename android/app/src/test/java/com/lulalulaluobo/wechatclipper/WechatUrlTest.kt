package com.lulalulaluobo.wechatclipper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class WechatUrlTest {
    @Test
    fun usesGcsbBackendByDefault() {
        assertEquals("https://wechat.lucc.fun", DEFAULT_SERVER_URL)
    }

    @Test
    fun extractsWechatArticleUrlFromSharedText() {
        assertEquals(
            "https://mp.weixin.qq.com/s/example?from=singlemessage",
            extractWechatUrl("文章链接：https://mp.weixin.qq.com/s/example?from=singlemessage。"),
        )
    }

    @Test
    fun rejectsNonWechatSharedText() {
        assertNull(extractWechatUrl("https://example.com/article"))
    }

    @Test
    fun prioritizesProcessingMessageWhileTasksAreActive() {
        assertEquals(
            "正在抓取文章并写入 Obsidian…",
            clipProgressMessage(
                listOf(
                    ClipTask("queued", "https://mp.weixin.qq.com/s/queued", "queued", "", ""),
                    ClipTask("processing", "https://mp.weixin.qq.com/s/processing", "processing", "", ""),
                ),
            ),
        )
    }

    @Test
    fun explainsThatQueuedTasksAreWaitingToRun() {
        assertEquals(
            "任务在队列中，正在等待转存…",
            clipProgressMessage(
                listOf(ClipTask("queued", "https://mp.weixin.qq.com/s/queued", "queued", "", "")),
            ),
        )
    }

    @Test
    fun hasNoProgressMessageWhenAllTasksAreFinal() {
        assertNull(
            clipProgressMessage(
                listOf(ClipTask("done", "https://mp.weixin.qq.com/s/done", "succeeded", "", "")),
            ),
        )
    }

    @Test
    fun parsesNewerSignedReleaseAssetWithSha256Digest() {
        val update = parseReleaseUpdate(
            """
            {
              "tag_name": "v1.1.0",
              "assets": [{
                "name": "Shijian-v1.1.0-5-release.apk",
                "browser_download_url": "https://github.com/lulalulaluobo/shijian-clipper/releases/download/v1.1.0/Shijian-v1.1.0-5-release.apk",
                "digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
              }]
            }
            """.trimIndent(),
            currentVersionCode = 4,
        )

        assertNotNull(update)
        assertEquals(5, update?.versionCode)
        assertEquals("1.1.0", update?.versionName)
    }

    @Test
    fun rejectsReleaseWithoutGithubSha256Digest() {
        assertNull(
            parseReleaseUpdate(
                """
                {
                  "tag_name": "v1.1.0",
                  "assets": [{
                    "name": "Shijian-v1.1.0-5-release.apk",
                    "browser_download_url": "https://github.com/lulalulaluobo/shijian-clipper/releases/download/v1.1.0/Shijian-v1.1.0-5-release.apk"
                  }]
                }
                """.trimIndent(),
                currentVersionCode = 4,
            ),
        )
    }

    @Test
    fun parsesGeneratedApiTokenAndTokenListMetadata() {
        val generated = apiTokenFrom(
            org.json.JSONObject("""{"id":"token-1","token":"sk_once","label":"Obsidian"}"""),
        )
        val tokens = apiTokensFrom(
            org.json.JSONArray("""[{"id":"token-1","label":"Obsidian","created":"2026-07-20T10:00:00Z"}]"""),
        )

        assertEquals("sk_once", generated.token)
        assertEquals("Obsidian", tokens.single().label)
        assertEquals("2026-07-20T10:00:00Z", tokens.single().created)
    }

    @Test
    fun ignoresReleaseThatIsNotNewerThanInstalledApp() {
        assertNull(
            parseReleaseUpdate(
                """
                {
                  "tag_name": "v1.0.1",
                  "assets": [{
                    "name": "Shijian-v1.0.1-4-release.apk",
                    "browser_download_url": "https://github.com/lulalulaluobo/shijian-clipper/releases/download/v1.0.1/Shijian-v1.0.1-4-release.apk",
                    "digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                  }]
                }
                """.trimIndent(),
                currentVersionCode = 4,
            ),
        )
    }
}
