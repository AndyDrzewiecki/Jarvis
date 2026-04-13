package com.jarvis.os

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.jarvis.os.device.DevicePreferences
import com.jarvis.os.device.DeviceProfile
import com.jarvis.os.device.KioskManager
import com.jarvis.os.network.ChatRequest
import com.jarvis.os.service.WebSocketService
import com.jarvis.os.network.JarvisApiClient
import com.jarvis.os.network.NotebookSaveRequest
import com.jarvis.os.ui.*
import com.jarvis.os.ui.theme.ArcReactorBg
import com.jarvis.os.ui.theme.JarvisTheme
import com.jarvis.os.updater.OtaUpdater
import com.jarvis.os.voice.TtsPlayer
import com.jarvis.os.voice.VoiceManager
import com.jarvis.os.voice.VoiceState
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var voiceManager: VoiceManager
    private lateinit var ttsPlayer: TtsPlayer
    private lateinit var devicePrefs: DevicePreferences

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        voiceManager = VoiceManager(this)
        ttsPlayer = TtsPlayer()
        devicePrefs = DevicePreferences(this)

        lifecycleScope.launch {
            val serverIp = devicePrefs.serverIp.first()
            OtaUpdater(this@MainActivity).checkAndUpdate(serverIp, BuildConfig.VERSION_CODE)
        }

        // Start persistent WebSocket push listener
        startService(Intent(this, WebSocketService::class.java))

        // Wire kiosk mode for launcher profiles (kitchen, garage, bedroom)
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
                    )
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        voiceManager.destroy()
        ttsPlayer.stopPlayback()
    }
}

@Composable
fun JarvisApp(
    voiceManager: VoiceManager,
    ttsPlayer: TtsPlayer,
    devicePrefs: DevicePreferences,
) {
    val navController = rememberNavController()
    val voiceState by voiceManager.state.collectAsState()

    var transcript by remember { mutableStateOf("") }
    var lastResponse by remember { mutableStateOf<JarvisResponse?>(null) }
    var notebookEntries by remember { mutableStateOf<List<NotebookEntry>>(emptyList()) }

    val serverIp by devicePrefs.serverIp.collectAsState(initial = DevicePreferences.DEFAULT_SERVER_IP)
    val deviceName by devicePrefs.deviceName.collectAsState(initial = android.os.Build.MODEL)
    val deviceProfile by devicePrefs.deviceProfile.collectAsState(initial = DeviceProfile.DEFAULT.profileName)

    val scope = rememberCoroutineScope()

    // Update transcript from voice state
    LaunchedEffect(voiceState) {
        when (val state = voiceState) {
            is VoiceState.Partial -> transcript = state.text
            is VoiceState.Error -> transcript = state.message
            is VoiceState.Idle -> { /* keep last transcript */ }
            is VoiceState.Listening -> transcript = ""
            is VoiceState.Result -> {
                transcript = state.text
                // Send to Jarvis server
                scope.launch {
                    try {
                        val api = JarvisApiClient.build(serverIp)
                        val response = api.chat(ChatRequest(state.text))
                        lastResponse = JarvisResponse(response.text, response.adapter)
                        ttsPlayer.play(serverIp, response.text, cacheDir)
                    } catch (e: Exception) {
                        transcript = "Connection error: ${e.message}"
                    }
                }
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
                            // Silently fail — notebook is non-critical
                        }
                    }
                },
                onSettingsClick = { navController.navigate("settings") },
                onNotebookClick = { navController.navigate("notebook") },
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
                        // Register device with server
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
