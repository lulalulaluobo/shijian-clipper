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
}
