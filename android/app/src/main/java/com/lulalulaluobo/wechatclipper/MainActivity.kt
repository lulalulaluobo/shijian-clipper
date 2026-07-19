package com.lulalulaluobo.wechatclipper

import android.content.Intent
import android.net.Uri
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Row
import androidx.compose.ui.Alignment
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private var sharedUrl by mutableStateOf<String?>(null)
    private var sharedFileUri by mutableStateOf<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
        setContent { AppTheme { ClipperApp(sharedUrl, sharedFileUri, { sharedUrl = null }, { sharedFileUri = null }) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND) {
            val streamUri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
            if (streamUri != null) {
                sharedFileUri = streamUri
                sharedUrl = null
            } else {
                val text = intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty()
                sharedUrl = extractWechatUrl(text)
                sharedFileUri = null
            }
        } else {
            sharedUrl = null
            sharedFileUri = null
        }
    }
}

fun extractWechatUrl(text: String): String? = Regex("https://mp\\.weixin\\.qq\\.com/s[^\\s]*")
    .find(text)?.value?.trimEnd('.', ',', '。', '，', '!', '！', ')', '）')

private enum class Page { CHAT, SETTINGS }
const val DEFAULT_SERVER_URL = "https://wechat.lucc.fun"

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
private fun ClipperApp(
    sharedUrl: String?,
    sharedFileUri: Uri?,
    onSharedHandled: () -> Unit,
    onSharedFileHandled: () -> Unit
) {
    val context = LocalContext.current.applicationContext
    val store = remember(context) { SessionStore(context) }
    var session by remember { mutableStateOf(store.load()) }
    var serverUrl by remember { mutableStateOf(store.loadServerUrl()) }
    var page by remember { mutableStateOf(Page.CHAT) }
    val activeSession = session

    if (activeSession == null) {
        AuthScreen(
            serverUrl = serverUrl,
            onAuthenticated = {
                store.save(it)
                serverUrl = it.baseUrl
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
            onServerChanged = {
                store.saveServerUrl(it)
                store.clear()
                serverUrl = it
                session = null
            },
        )
    } else {
        ChatScreen(
            session = activeSession,
            sharedUrl = sharedUrl,
            sharedFileUri = sharedFileUri,
            onSharedHandled = onSharedHandled,
            onSharedFileHandled = onSharedFileHandled,
            onOpenSettings = { page = Page.SETTINGS },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AuthScreen(serverUrl: String, onAuthenticated: (Session) -> Unit) {
    var isRegistering by remember { mutableStateOf(false) }
    var inputServerUrl by remember { mutableStateOf(serverUrl) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var inviteCode by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("填写你的服务地址后登录。") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Scaffold(topBar = { TopAppBar(title = { Text("拾笺") }) }) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(if (isRegistering) "使用邀请码创建账户" else "登录你的转存服务", style = MaterialTheme.typography.headlineSmall)
            Text(message, style = MaterialTheme.typography.bodyMedium)
            OutlinedTextField(inputServerUrl, { inputServerUrl = it }, Modifier.fillMaxWidth(), label = { Text("服务地址（HTTPS）") }, singleLine = true)
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
                            val normalizedUrl = normalizeServerUrl(inputServerUrl)
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
private fun ChatScreen(
    session: Session,
    sharedUrl: String?,
    sharedFileUri: Uri?,
    onSharedHandled: () -> Unit,
    onSharedFileHandled: () -> Unit,
    onOpenSettings: () -> Unit
) {
    val client = remember(session) { ApiClient(session.baseUrl, session.token) }
    val context = LocalContext.current
    var draft by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("从微信分享文章，或粘贴公众号链接。") }
    var tasks by remember { mutableStateOf(emptyList<ClipTask>()) }
    var busy by remember { mutableStateOf(false) }
    var handledShare by remember { mutableStateOf<String?>(null) }
    var handledShareFile by remember { mutableStateOf<Uri?>(null) }
    val scope = rememberCoroutineScope()

    suspend fun refresh(updateMessage: Boolean = false) {
        try {
            val updatedTasks = withContext(Dispatchers.IO) { client.listClips() }
            tasks = updatedTasks
            if (updateMessage) {
                message = clipProgressMessage(updatedTasks) ?: "转存状态已更新。"
            }
        } catch (error: Exception) {
            message = error.userMessage()
        }
    }
    
    fun uploadFile(uri: Uri) {
        val fileData = readUriContent(context, uri)
        if (fileData == null) {
            message = "读取选定文件失败。"
            return
        }
        val (filename, content) = fileData
        busy = true
        message = "正在上传附件 $filename..."
        scope.launch {
            try {
                var progressText by mutableStateOf("正在上传附件 $filename: 0%")
                message = progressText
                val result = withContext(Dispatchers.IO) {
                    client.uploadAttachment(filename, content) { progress ->
                        progressText = "正在上传附件 $filename: $progress%"
                        message = progressText
                    }
                }
                message = "${result.filename} 已上传，等待 Obsidian 同步"
                refresh()
            } catch (error: Exception) {
                message = error.userMessage()
            } finally {
                busy = false
            }
        }
    }

    val filePickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent(),
        onResult = { uri ->
            if (uri != null) {
                uploadFile(uri)
            }
        }
    )

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
                message = clipProgressMessage(listOf(task)) ?: "转存状态已更新。"
            } catch (error: Exception) {
                message = error.userMessage()
            } finally {
                busy = false
            }
        }
    }

    val hasActiveTasks = tasks.any { it.status == "queued" || it.status == "processing" }

    LaunchedEffect(session) { refresh() }
    LaunchedEffect(session, hasActiveTasks) {
        while (hasActiveTasks) {
            delay(2_000)
            refresh(updateMessage = true)
        }
    }
    LaunchedEffect(sharedUrl, session.token) {
        if (sharedUrl != null && sharedUrl != handledShare) {
            handledShare = sharedUrl
            draft = sharedUrl
            submit(sharedUrl)
            onSharedHandled()
        }
    }
    LaunchedEffect(sharedFileUri, session.token) {
        if (sharedFileUri != null && sharedFileUri != handledShareFile) {
            handledShareFile = sharedFileUri
            uploadFile(sharedFileUri)
            onSharedFileHandled()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("拾笺") },
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
                            val retriedTask = withContext(Dispatchers.IO) { client.retryClip(task.id) }
                            tasks = tasks.map { current -> if (current.id == retriedTask.id) retriedTask else current }
                            message = clipProgressMessage(listOf(retriedTask)) ?: "转存状态已更新。"
                        } catch (error: Exception) {
                            message = error.userMessage()
                        }
                    }
                }) }
            }
            OutlinedTextField(draft, { draft = it }, Modifier.fillMaxWidth(), label = { Text("粘贴公众号文章链接") }, minLines = 2)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = { filePickerLauncher.launch("*/*") },
                    modifier = Modifier.weight(1f),
                    enabled = !busy
                ) {
                    Text("📎 上传附件")
                }
                Button(
                    onClick = { submit(draft) },
                    modifier = Modifier.weight(1f),
                    enabled = !busy
                ) {
                    Text(if (busy) "正在提交…" else "发送转存任务")
                }
            }
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
            if (task.status == "failed" && !task.sourceUrl.startsWith("https://attachment.local/")) {
                TextButton(onClick = { onRetry(task) }) { Text("重试") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SettingsScreen(session: Session, onBack: () -> Unit, onLogout: () -> Unit, onServerChanged: (String) -> Unit) {
    val client = remember(session) { ApiClient(session.baseUrl, session.token) }
    val context = LocalContext.current
    var canCreateInvites by remember { mutableStateOf(false) }
    var inviteCode by remember { mutableStateOf("") }
    var serverUrl by remember { mutableStateOf(session.baseUrl) }
    var message by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var availableUpdate by remember { mutableStateOf<ReleaseUpdate?>(null) }
    var updateMessage by remember { mutableStateOf("正在检查应用更新…") }
    var checkingUpdate by remember { mutableStateOf(false) }
    var updating by remember { mutableStateOf(false) }
    var showUpdateConfirmation by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun checkForUpdate(showCurrentVersion: Boolean) {
        checkingUpdate = true
        try {
            availableUpdate = withContext(Dispatchers.IO) { UpdateClient.checkForUpdate(BuildConfig.VERSION_CODE) }
            updateMessage = availableUpdate?.let { "发现新版本 v${it.versionName}" }
                ?: if (showCurrentVersion) "当前已是最新版本。" else "已是最新版本。"
        } catch (error: Exception) {
            updateMessage = error.message ?: "无法检查更新，请稍后重试。"
        } finally {
            checkingUpdate = false
        }
    }

    LaunchedEffect(session) {
        try {
            canCreateInvites = withContext(Dispatchers.IO) { client.canCreateInvites() }
        } catch (error: Exception) {
            message = error.userMessage()
        }
    }
    LaunchedEffect(Unit) { checkForUpdate(showCurrentVersion = false) }

    Scaffold(topBar = { TopAppBar(title = { Text("设置") }, navigationIcon = { TextButton(onClick = onBack) { Text("返回") } }) }) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(20.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Obsidian 同步", style = MaterialTheme.typography.headlineSmall)
            Text("文章将在抓取后自动同步到你的 Obsidian 插件。请在 Obsidian 中安装「拾笺同步」插件并登录本服务账号。", style = MaterialTheme.typography.bodyMedium)
            if (message.isNotBlank()) Text(message, style = MaterialTheme.typography.bodyMedium)
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
                                            putExtra(Intent.EXTRA_TEXT, "邀请你使用拾笺。\n服务地址：${session.baseUrl}\n邀请码：$inviteCode")
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
            Text("服务端", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(serverUrl, { serverUrl = it }, Modifier.fillMaxWidth(), label = { Text("服务地址（HTTPS）") }, singleLine = true)
            Button(
                onClick = {
                    try {
                        onServerChanged(normalizeServerUrl(serverUrl))
                    } catch (error: Exception) {
                        message = error.userMessage()
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy && serverUrl.trim().removeSuffix("/") != session.baseUrl,
            ) { Text("切换服务端并重新登录") }
            Spacer(Modifier.height(16.dp))
            Text("关于", style = MaterialTheme.typography.titleMedium)
            Text("拾笺 · v${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})", style = MaterialTheme.typography.bodyMedium)
            TextButton(
                onClick = {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/lulalulaluobo/shijian-clipper")))
                },
            ) { Text("GitHub 项目主页") }
            if (availableUpdate != null) {
                Text(updateMessage, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.titleSmall)
                Button(
                    onClick = { showUpdateConfirmation = true },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !updating,
                ) { Text(if (updating) "正在校验更新…" else "下载并安装 v${availableUpdate?.versionName}") }
            } else {
                Text(updateMessage, style = MaterialTheme.typography.bodySmall)
                TextButton(
                    onClick = { scope.launch { checkForUpdate(showCurrentVersion = true) } },
                    enabled = !checkingUpdate,
                ) { Text(if (checkingUpdate) "正在检查…" else "检查更新") }
            }
            TextButton(onClick = onLogout) { Text("退出登录") }
        }
    }

    val update = availableUpdate
    if (showUpdateConfirmation && update != null) {
        AlertDialog(
            onDismissRequest = { showUpdateConfirmation = false },
            title = { Text("安装 v${update.versionName}？") },
            text = { Text("将从 GitHub Release 下载 APK，并校验 SHA-256、包名、版本号与当前签名。校验通过后，仍需你在 Android 系统安装页确认。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showUpdateConfirmation = false
                        updating = true
                        scope.launch {
                            try {
                                updateMessage = "正在下载并校验更新…"
                                val apkFile = withContext(Dispatchers.IO) { UpdateClient.downloadAndVerify(context, update) }
                                if (!UpdateClient.canRequestInstalls(context)) {
                                    updateMessage = "更新已校验。请允许拾笺安装未知应用后，再点击安装。"
                                    UpdateClient.openInstallPermissionSettings(context)
                                } else {
                                    updateMessage = "更新已校验，Android 将请求你的安装确认。"
                                    UpdateClient.requestUserConfirmedInstall(context, apkFile)
                                }
                            } catch (error: Exception) {
                                updateMessage = error.message ?: "更新失败，请稍后重试。"
                            } finally {
                                updating = false
                            }
                        }
                    },
                ) { Text("下载并校验") }
            },
            dismissButton = { TextButton(onClick = { showUpdateConfirmation = false }) { Text("取消") } },
        )
    }
}

private fun ClipTask.statusLabel(): String = when (status) {
    "queued" -> "等待转存"
    "processing" -> "正在抓取并写入"
    "succeeded" -> "已写入 Obsidian"
    "failed" -> "转存失败"
    else -> status
}

fun clipProgressMessage(tasks: List<ClipTask>): String? = when {
    tasks.any { it.status == "processing" } -> "正在抓取文章并写入 Obsidian…"
    tasks.any { it.status == "queued" } -> "任务在队列中，正在等待转存…"
    else -> null
}

private fun normalizeServerUrl(value: String): String {
    val normalized = value.trim().removeSuffix("/")
    require(normalized.startsWith("https://") && normalized.length > "https://".length) { "服务地址必须是有效的 HTTPS 地址。" }
    return normalized
}

private fun Throwable.userMessage(): String = (this as? ApiException)?.message ?: "请求失败，请检查网络和服务地址。"

fun readUriContent(context: android.content.Context, uri: Uri): Pair<String, ByteArray>? {
    val contentResolver = context.contentResolver
    var filename = "attachment"
    contentResolver.query(uri, null, null, null, null)?.use { cursor ->
        val nameIndex = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
        if (nameIndex != -1 && cursor.moveToFirst()) {
            filename = cursor.getString(nameIndex)
        }
    }
    return try {
        val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
        filename to bytes
    } catch (_: Exception) {
        null
    }
}

