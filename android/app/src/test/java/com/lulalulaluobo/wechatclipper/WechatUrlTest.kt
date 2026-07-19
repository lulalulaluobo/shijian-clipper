package com.lulalulaluobo.wechatclipper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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
}
