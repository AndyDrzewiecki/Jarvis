package com.jarvis.os.service

import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.jarvis.os.device.DevicePreferences
import com.jarvis.os.notification.NotificationHelper
import com.jarvis.os.voice.TtsPlayer
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import okhttp3.*
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Persistent foreground service that maintains a WebSocket connection to the
 * Jarvis server for real-time push messages.
 *
 * Supported message types:
 *   {"type":"speak","text":"..."}   — plays the text via TTS
 *   {"type":"alert","title":"...","message":"..."}  — posts a visible notification
 *   {"type":"notify","text":"..."}  — alias for alert with generic title
 *
 * Reconnects with exponential backoff: 2s → 4s → 8s → … → 60s max.
 */
class WebSocketService : Service() {

    companion object {
        private const val TAG = "WebSocketService"
        private const val NOTIFICATION_ID = 1001
        private const val BACKOFF_BASE_MS = 2_000L
        private const val BACKOFF_MAX_MS = 60_000L
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private lateinit var devicePrefs: DevicePreferences
    private lateinit var ttsPlayer: TtsPlayer
    private var currentSocket: WebSocket? = null
    private var reconnectDelayMs = BACKOFF_BASE_MS

    override fun onCreate() {
        super.onCreate()
        devicePrefs = DevicePreferences(this)
        ttsPlayer = TtsPlayer()
        NotificationHelper.createChannels(this)
        startForeground(NOTIFICATION_ID, NotificationHelper.buildPushServiceNotification(this, "Connecting…"))
        scope.launch { connectLoop() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        currentSocket?.close(1000, "Service stopped")
        scope.cancel()
    }

    // ── Connection loop ───────────────────────────────────────────────────────

    private suspend fun connectLoop() {
        val serverIp = devicePrefs.serverIp.first()
        val deviceName = devicePrefs.deviceName.first()
        val deviceId = deviceName.lowercase().replace(" ", "-")

        while (scope.isActive) {
            val url = "ws://$serverIp/api/ws?device_id=$deviceId"
            Log.d(TAG, "Connecting to $url")

            val connected = connectOnce(url, serverIp)
            if (connected) {
                reconnectDelayMs = BACKOFF_BASE_MS
            } else {
                Log.w(TAG, "WebSocket disconnected. Retrying in ${reconnectDelayMs}ms.")
                updateStatus("Reconnecting…")
                delay(reconnectDelayMs)
                reconnectDelayMs = minOf(reconnectDelayMs * 2, BACKOFF_MAX_MS)
            }
        }
    }

    private suspend fun connectOnce(url: String, serverIp: String): Boolean {
        val connected = CompletableDeferred<Boolean>()
        val disconnected = CompletableDeferred<Unit>()

        val request = Request.Builder().url(url).build()
        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                currentSocket = webSocket
                updateStatus("Connected")
                connected.complete(true)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text, serverIp)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WebSocket failure: ${t.message}")
                if (!connected.isCompleted) connected.complete(false)
                disconnected.complete(Unit)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code $reason")
                disconnected.complete(Unit)
            }
        }

        client.newWebSocket(request, listener)

        return try {
            val wasConnected = connected.await()
            if (wasConnected) disconnected.await()
            wasConnected
        } catch (e: Exception) {
            false
        }
    }

    // ── Message handling ──────────────────────────────────────────────────────

    private fun handleMessage(text: String, serverIp: String) {
        try {
            val json = JSONObject(text)
            when (json.optString("type")) {
                "speak" -> {
                    val speakText = json.optString("text")
                    if (speakText.isNotBlank()) {
                        scope.launch(Dispatchers.IO) {
                            ttsPlayer.play(serverIp, speakText, cacheDir)
                        }
                    }
                }

                "alert" -> {
                    val title = json.optString("title").ifBlank { "Jarvis Alert" }
                    val message = json.optString("message").ifBlank { json.optString("text") }
                    if (message.isNotBlank()) {
                        NotificationHelper.postAlert(this, title, message)
                    }
                }

                "notify" -> {
                    val message = json.optString("text").ifBlank { json.optString("message") }
                    if (message.isNotBlank()) {
                        NotificationHelper.postAlert(this, "Jarvis", message)
                    }
                }

                else -> Log.d(TAG, "Unknown WS message type: $text")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse WS message: $text")
        }
    }

    // ── Notification helpers ──────────────────────────────────────────────────

    private fun updateStatus(status: String) {
        getSystemService(NotificationManager::class.java)
            ?.notify(NOTIFICATION_ID, NotificationHelper.buildPushServiceNotification(this, status))
    }
}
