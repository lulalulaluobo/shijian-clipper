package com.lulalulaluobo.wechatclipper

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private var sharedUrl by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sharedUrl = extractWechatUrl(intent?.getStringExtra(Intent.EXTRA_TEXT).orEmpty())
        setContent { AppTheme { ClipperApp(sharedUrl) { sharedUrl = null } } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        sharedUrl = extractWechatUrl(intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty())
    }
}

fun extractWechatUrl(text: String): String? = Regex("https://mp\\.weixin\\.qq\\.com/s[^\\s]*")
    .find(text)?.value?.trimEnd('.', ',', '。', '，', '!', '！', ')', '）')

private enum class Page { CHAT, SETTINGS }

@Composable
private fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF236247),
            onPrimary = Color.White,
            background = Color(0xFFF7F6F1),
            surface = Color(0xFFFFFEFA),
            onSurface = Color(0xFF1B1C1A),
        ),
        content = content,
    )
}

@Composable
private fun ClipperApp(sharedUrl: String?, onSharedHandled: () -> Unit) {
    val context = LocalContext.current.applicationContext
    val store = remember(context) { SessionStore(context) }
    var session by remember { mutableStateOf(store.load()) }
    var page by remember { mutableStateOf(Page.CHAT) }
    val activeSession = session

    if (activeSession == null) {
        AuthScreen(
            onAuthenticated = {
                store.save(it)
                session = it
            },
        )
    } else if (page == Page.SETTINGS) {
        SettingsScreen(
            session = activeSession,
            onBack = { page = Page.CHAT },
            onLogout = {
                store.clear()
                session = null
            },
        )
    } else {
        ChatScreen(
            session = activeSession,
            sharedUrl = sharedUrl,
            onSharedHandled = onSharedHandled,
            onOpenSettings = { page = Page.SETTINGS },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AuthScreen(onAuthenticated: (Session) -> Unit) {
    var isRegistering by remember { mutableStateOf(false) }
    var serverUrl by remember { mutableStateOf("https://") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var inviteCode by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("填写你的服务地址后登录。") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Scaffold(topBar = { TopAppBar(title = { Text("转存助手") }) }) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(if (isRegistering) "使用邀请码创建账户" else "登录你的转存服务", style = MaterialTheme.typography.headlineSmall)
            Text(message, style = MaterialTheme.typography.bodyMedium)
            OutlinedTextField(serverUrl, { serverUrl = it }, Modifier.fillMaxWidth(), label = { Text("服务地址（HTTPS）") }, singleLine = true)
            if (isRegistering) {
                OutlinedTextField(inviteCode, { inviteCode = it }, Modifier.fillMaxWidth(), label = { Text("邀请码") }, singleLine = true)
            }
            OutlinedTextField(email, { email = it }, Modifier.fillMaxWidth(), label = { Text("邮箱") }, singleLine = true)
            OutlinedTextField(
                password,
                { password = it },
                Modifier.fillMaxWidth(),
                label = { Text("密码") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
            )
            Button(
                onClick = {
                    busy = true
                    scope.launch {
                        try {
                            val normalizedUrl = normalizeServerUrl(serverUrl)
                            val client = ApiClient(normalizedUrl)
                            val nextSession = withContext(Dispatchers.IO) {
                                if (isRegistering) client.register(inviteCode, email, password)
                                client.login(email, password)
                            }
                            onAuthenticated(nextSession.copy(baseUrl = normalizedUrl))
                        } catch (error: Exception) {
                            message = error.userMessage()
                        } finally {
                            busy = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy,
            ) { Text(if (busy) "处理中…" else if (isRegistering) "注册并登录" else "登录") }
            TextButton(onClick = { isRegistering = !isRegistering }) {
                Text(if (isRegistering) "已有账户？去登录" else "有邀请码？创建账户")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChatScreen(session: Session, sharedUrl: String?, onSharedHandled: () -> Unit, onOpenSettings: () -> Unit) {
    val client = remember(session) { ApiClient(session.baseUrl, session.token) }
    var draft by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("从微信分享文章，或粘贴公众号链接。") }
    var tasks by remember { mutableStateOf(emptyList<ClipTask>()) }
    var busy by remember { mutableStateOf(false) }
    var handledShare by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun refresh() {
        scope.launch {
            try {
                tasks = withContext(Dispatchers.IO) { client.listClips() }
            } catch (error: Exception) {
                message = error.userMessage()
            }
        }
    }
    fun submit(url: String) {
        if (extractWechatUrl(url) == null) {
            message = "仅支持 HTTPS 微信公众号文章链接。"
            return
        }
        busy = true
        scope.launch {
            try {
                val task = withContext(Dispatchers.IO) { client.createClip(url) }
                tasks = listOf(task) + tasks
                draft = ""
                message = "已加入转存队列。"
            } catch (error: Exception) {
                message = error.userMessage()
            } finally {
                busy = false
            }
        }
    }

    LaunchedEffect(session) { refresh() }
    LaunchedEffect(sharedUrl, session.token) {
        if (sharedUrl != null && sharedUrl != handledShare) {
            handledShare = sharedUrl
            draft = sharedUrl
            submit(sharedUrl)
            onSharedHandled()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("转存助手") },
                actions = { TextButton(onClick = onOpenSettings) { Text("设置") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(message, style = MaterialTheme.typography.bodyMedium)
            Column(modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (tasks.isEmpty()) Text("还没有转存任务。", style = MaterialTheme.typography.bodySmall)
                tasks.forEach { TaskCard(it, onRetry = { task ->
                    scope.launch {
                        try {
                            withContext(Dispatchers.IO) { client.retryClip(task.id) }
                            message = "任务已重新加入队列。"
                            refresh()
                        } catch (error: Exception) {
                            message = error.userMessage()
                        }
                    }
                }) }
            }
            OutlinedTextField(draft, { draft = it }, Modifier.fillMaxWidth(), label = { Text("粘贴公众号文章链接") }, minLines = 2)
            Button(onClick = { submit(draft) }, modifier = Modifier.fillMaxWidth(), enabled = !busy) { Text(if (busy) "正在提交…" else "发送转存任务") }
        }
    }
}

@Composable
private fun TaskCard(task: ClipTask, onRetry: (ClipTask) -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(task.title.ifBlank { task.sourceUrl }, style = MaterialTheme.typography.bodyLarge)
            Text(task.statusLabel(), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            if (task.errorMessage.isNotBlank()) Text(task.errorMessage, style = MaterialTheme.typography.bodySmall)
            if (task.status == "failed") TextButton(onClick = { onRetry(task) }) { Text("重试") }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SettingsScreen(session: Session, onBack: () -> Unit, onLogout: () -> Unit) {
    val client = remember(session) { ApiClient(session.baseUrl, session.token) }
    val context = LocalContext.current
    var config by remember { mutableStateOf("") }
    var targetDir by remember { mutableStateOf("") }
    var summary by remember { mutableStateOf<FnsSettings?>(null) }
    var canCreateInvites by remember { mutableStateOf(false) }
    var inviteCode by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("保存 FNS JSON 后，令牌只保存在服务端加密存储中。") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(session) {
        try {
            summary = withContext(Dispatchers.IO) { client.getFnsSettings() }
            targetDir = summary?.targetDir.orEmpty()
            canCreateInvites = withContext(Dispatchers.IO) { client.canCreateInvites() }
        } catch (error: Exception) {
            message = error.userMessage()
        }
    }

    Scaffold(topBar = { TopAppBar(title = { Text("设置") }, navigationIcon = { TextButton(onClick = onBack) { Text("返回") } }) }) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(20.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Fast Note Sync", style = MaterialTheme.typography.headlineSmall)
            Text(message, style = MaterialTheme.typography.bodyMedium)
            if (summary?.configured == true) Text("已连接至 ${summary?.vault} · ${summary?.baseUrl}", style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(config, { config = it }, Modifier.fillMaxWidth(), label = { Text("FNS API 配置 JSON") }, minLines = 5)
            OutlinedTextField(targetDir, { targetDir = it }, Modifier.fillMaxWidth(), label = { Text("Obsidian 目标目录") }, singleLine = true)
            Button(
                onClick = {
                    busy = true
                    scope.launch {
                        try {
                            summary = withContext(Dispatchers.IO) { client.saveFnsSettings(config, targetDir) }
                            config = ""
                            message = "已安全保存配置。"
                        } catch (error: Exception) {
                            message = error.userMessage()
                        } finally {
                            busy = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy,
            ) { Text(if (busy) "正在保存…" else "保存配置") }
            Button(
                onClick = {
                    busy = true
                    scope.launch {
                        try {
                            val checked = withContext(Dispatchers.IO) { client.checkFnsSettings() }
                            message = when {
                                !checked.vaultChecked -> "连接成功；当前 token 无权限读取仓库列表，将按填写的仓库写入。"
                                checked.vaultExists -> "连接成功，已找到目标仓库。"
                                else -> "连接成功，但未找到这个仓库。"
                            }
                        } catch (error: Exception) {
                            message = error.userMessage()
                        } finally {
                            busy = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = summary?.configured == true && !busy,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary),
            ) { Text("检测连接（不写入笔记）") }
            if (canCreateInvites) {
                Spacer(Modifier.height(12.dp))
                Text("成员邀请", style = MaterialTheme.typography.titleMedium)
                Text("邀请码仅能注册一次。", style = MaterialTheme.typography.bodySmall)
                Button(
                    onClick = {
                        busy = true
                        scope.launch {
                            try {
                                inviteCode = withContext(Dispatchers.IO) { client.createInvite() }
                                context.startActivity(
                                    Intent.createChooser(
                                        Intent(Intent.ACTION_SEND).apply {
                                            type = "text/plain"
                                            putExtra(Intent.EXTRA_TEXT, "邀请你使用转存助手。\n服务地址：${session.baseUrl}\n邀请码：$inviteCode")
                                        },
                                        "分享邀请码",
                                    ),
                                )
                                message = "邀请码已生成，可分享给一位新用户。"
                            } catch (error: Exception) {
                                message = error.userMessage()
                            } finally {
                                busy = false
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !busy,
                ) { Text("生成并分享邀请码") }
                if (inviteCode.isNotBlank()) Text("邀请码：$inviteCode", style = MaterialTheme.typography.bodyMedium)
            }
            Spacer(Modifier.height(16.dp))
            Text("服务地址：${session.baseUrl}", style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = onLogout) { Text("退出登录") }
        }
    }
}

private fun ClipTask.statusLabel(): String = when (status) {
    "queued" -> "等待转存"
    "processing" -> "正在转存"
    "succeeded" -> "已写入 Obsidian"
    "failed" -> "转存失败"
    else -> status
}

private fun normalizeServerUrl(value: String): String {
    val normalized = value.trim().removeSuffix("/")
    require(normalized.startsWith("https://") && normalized.length > "https://".length) { "服务地址必须是有效的 HTTPS 地址。" }
    return normalized
}

private fun Throwable.userMessage(): String = (this as? ApiException)?.message ?: "请求失败，请检查网络和服务地址。"
