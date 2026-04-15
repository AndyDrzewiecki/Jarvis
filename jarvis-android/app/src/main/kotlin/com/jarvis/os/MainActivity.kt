package com.jarvis.os

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.jarvis.os.chat.ChatRepository
import com.jarvis.os.chat.ChatScreen
import com.jarvis.os.chat.ChatViewModel
import com.jarvis.os.device.DevicePreferences
import com.jarvis.os.device.DeviceProfile
import com.jarvis.os.device.KioskManager
import com.jarvis.os.network.ChatRequest
import com.jarvis.os.network.JarvisApiClient
import com.jarvis.os.network.NotebookSaveRequest
import com.jarvis.os.notification.NotificationHelper
import com.jarvis.os.service.WebSocketService
import com.jarvis.os.ui.*
import com.jarvis.os.ui.theme.ArcReactorBg
import com.jarvis.os.ui.theme.JarvisTheme
import com.jarvis.os.updater.OtaUpdater
import com.jarvis.os.voice.TtsPlayer
import com.jarvis.os.voice.VoiceManager
import com.jarvis.os.voice.VoiceState
import com.jarvis.os.voice.WakeWordService
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var voiceManager: VoiceManager
    private lateinit var ttsPlayer: TtsPlayer
    private lateinit var devicePrefs: DevicePreferences
    private lateinit var chatViewModel: ChatViewModel

    // Receives "Hey Jarvis" broadcasts from WakeWordService
    private val wakeWordReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != WakeWordService.ACTION_WAKE_WORD_DETECTED) return
            val command = intent.getStringExtra(WakeWordService.EXTRA_COMMAND) ?: ""
            if (command.isNotBlank()) {
                // Wake word came with an inline command — send it directly
                chatViewModel.sendMessage(command)
            } else {
                // Just the wake word — start listening for a follow-up command
                voiceManager.startListening()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        NotificationHelper.createChannels(this)

        voiceManager = VoiceManager(this)
        ttsPlayer = TtsPlayer()
        devicePrefs = DevicePreferences(this)

        // OTA check
        lifecycleScope.launch {
            val serverIp = devicePrefs.serverIp.first()
            OtaUpdater(this@MainActivity).checkAndUpdate(serverIp, BuildConfig.VERSION_CODE)
        }

        // Start persistent services
        startServiceCompat(WebSocketService::class.java)
        startServiceCompat(WakeWordService::class.java)

        // Register wake-word broadcast receiver
        val filter = IntentFilter(WakeWordService.ACTION_WAKE_WORD_DETECTED)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(wakeWordReceiver, filter, RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(wakeWordReceiver, filter)
        }

        // Kiosk mode for launcher profiles
        lifecycleScope.launch {
            devicePrefs.deviceProfile.collectLatest { profileName ->
                val profile = DeviceProfile.fromName(profileName)
                if (profile.isLauncherMode) {
                    KioskManager(this@MainActivity).enterKioskMode()
                }
            }
        }

        setContent {
            JarvisTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = ArcReactorBg) {
                    JarvisApp(
                        voiceManager = voiceManager,
                        ttsPlayer = ttsPlayer,
                        devicePrefs = devicePrefs,
                        chatViewModelFactory = { serverIp ->
                            ChatViewModel.Factory(ChatRepository(serverIp)).also { factory ->
                                chatViewModel = ViewModelProvider(this, factory)[ChatViewModel::class.java]
                            }.let { chatViewModel }
                        },
                    )
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        unregisterReceiver(wakeWordReceiver)
        voiceManager.destroy()
        ttsPlayer.stopPlayback()
    }

    private fun startServiceCompat(clazz: Class<*>) {
        val intent = Intent(this, clazz)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}

@Composable
fun JarvisApp(
    voiceManager: VoiceManager,
    ttsPlayer: TtsPlayer,
    devicePrefs: DevicePreferences,
    chatViewModelFactory: @Composable (serverIp: String) -> ChatViewModel,
) {
    val navController = rememberNavController()
    val voiceState by voiceManager.state.collectAsState()

    var transcript by remember { mutableStateOf("") }
    var lastResponse by remember { mutableStateOf<JarvisResponse?>(null) }
    var notebookEntries by remember { mutableStateOf<List<NotebookEntry>>(emptyList()) }

    val serverIp by devicePrefs.serverIp.collectAsState(initial = DevicePreferences.DEFAULT_SERVER_IP)
    val deviceName by devicePrefs.deviceName.collectAsState(initial = android.os.Build.MODEL)
    val deviceProfile by devicePrefs.deviceProfile.collectAsState(initial = DeviceProfile.DEFAULT.profileName)

    // Build the ChatViewModel once we know the server IP
    val chatViewModel = chatViewModelFactory(serverIp)
    val chatUiState by chatViewModel.uiState.collectAsState()

    val scope = rememberCoroutineScope()

    // Update transcript from voice state; on final result, route to ChatViewModel
    LaunchedEffect(voiceState) {
        when (val state = voiceState) {
            is VoiceState.Partial -> transcript = state.text
            is VoiceState.Error -> transcript = state.message
            is VoiceState.Idle -> { /* keep last transcript */ }
            is VoiceState.Listening -> transcript = ""
            is VoiceState.Result -> {
                transcript = state.text
                chatViewModel.sendMessage(state.text)
                // TTS is handled by observing chatUiState.messages below
            }
        }
    }

    // Play TTS for the latest Jarvis response
    LaunchedEffect(chatUiState.messages) {
        val last = chatUiState.messages.lastOrNull()
        if (last != null && last.isJarvis && last.text.isNotBlank()) {
            scope.launch {
                ttsPlayer.play(serverIp, last.text, /* cacheDir placeholder */ java.io.File(""))
            }
        }
    }

    NavHost(navController = navController, startDestination = "home") {

        composable("home") {
            HomeScreen(
                isListening = voiceState is VoiceState.Listening || voiceState is VoiceState.Partial,
                transcript = transcript,
                lastResponse = lastResponse,
                deviceName = deviceName,
                onVoiceButtonClick = {
                    if (voiceState is VoiceState.Listening || voiceState is VoiceState.Partial) {
                        voiceManager.stopListening()
                    } else {
                        voiceManager.startListening()
                    }
                },
                onSaveToNotebook = { content ->
                    scope.launch {
                        try {
                            val api = JarvisApiClient.build(serverIp)
                            api.saveToNotebook(
                                NotebookSaveRequest(
                                    content = content,
                                    category = "saved_items",
                                    deviceId = deviceName,
                                )
                            )
                        } catch (e: Exception) {
                            // Notebook save is non-critical
                        }
                    }
                },
                onSettingsClick = { navController.navigate("settings") },
                onNotebookClick = { navController.navigate("notebook") },
                onChatClick = { navController.navigate("chat") },
            )
        }

        composable("chat") {
            ChatScreen(
                uiState = chatUiState,
                isListening = voiceState is VoiceState.Listening || voiceState is VoiceState.Partial,
                voiceTranscript = transcript,
                onSendMessage = { chatViewModel.sendMessage(it) },
                onVoiceButtonClick = {
                    if (voiceState is VoiceState.Listening || voiceState is VoiceState.Partial) {
                        voiceManager.stopListening()
                    } else {
                        voiceManager.startListening()
                    }
                },
                onBack = { navController.popBackStack() },
            )
        }

        composable("settings") {
            SettingsScreen(
                serverIp = serverIp,
                deviceName = deviceName,
                deviceProfile = deviceProfile,
                onSave = { ip, name, profile ->
                    scope.launch {
                        devicePrefs.saveServerIp(ip)
                        devicePrefs.saveDeviceName(name)
                        devicePrefs.saveDeviceProfile(profile)
                        try {
                            val api = JarvisApiClient.build(ip)
                            api.registerDevice(
                                com.jarvis.os.network.DeviceRegisterRequest(
                                    deviceId = name.lowercase().replace(" ", "-"),
                                    profile = profile,
                                    displayName = name,
                                )
                            )
                        } catch (e: Exception) {
                            // Registration failure is non-fatal
                        }
                        navController.popBackStack()
                    }
                },
            )
        }

        composable("notebook") {
            NotebookScreen(
                entries = notebookEntries,
                onSearch = { query ->
                    scope.launch {
                        try {
                            val api = JarvisApiClient.build(serverIp)
                            val result = api.getNotebook(query = query.ifBlank { null })
                            @Suppress("UNCHECKED_CAST")
                            val items = (result["items"] as? List<Map<String, Any>>) ?: emptyList()
                            notebookEntries = items.map { item ->
                                NotebookEntry(
                                    id = item["id"]?.toString() ?: "",
                                    title = item["title"]?.toString() ?: "",
                                    content = item["content"]?.toString() ?: "",
                                    category = item["category"]?.toString() ?: "notes",
                                    deviceId = item["device_id"]?.toString() ?: "",
                                    createdAt = item["created_at"]?.toString() ?: "",
                                )
                            }
                        } catch (e: Exception) {
                            // Keep existing entries on error
                        }
                    }
                },
                onBack = { navController.popBackStack() },
            )
        }
    }
}
