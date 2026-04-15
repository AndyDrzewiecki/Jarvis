package com.jarvis.os.voice

import android.app.Service
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import com.jarvis.os.notification.NotificationHelper
import java.util.Locale

/**
 * Always-on foreground service for "Hey Jarvis" wake-word detection.
 *
 * Strategy: run Android's SpeechRecognizer in a tight loop. On each session,
 * scan results for any of [WAKE_PHRASES]. When found, extract the trailing
 * command and broadcast [ACTION_WAKE_WORD_DETECTED] so MainActivity can
 * activate the full voice input flow.
 *
 * SpeechRecognizer requires the main thread — everything here runs on a
 * [Handler] backed by [Looper.getMainLooper()].
 *
 * No third-party libraries needed (no Porcupine license required).
 */
class WakeWordService : Service() {

    companion object {
        const val TAG = "WakeWordService"
        const val NOTIFICATION_ID = 1002

        /** Broadcast action emitted when wake word is detected. */
        const val ACTION_WAKE_WORD_DETECTED = "com.jarvis.os.WAKE_WORD_DETECTED"

        /** Extra: the command text spoken after the wake phrase (may be empty). */
        const val EXTRA_COMMAND = "command"

        /** Recognized wake phrases (all lowercase for comparison). */
        val WAKE_PHRASES = setOf("hey jarvis", "ok jarvis", "jarvis")

        /** Pause between recognition sessions (ms). */
        private const val RESTART_DELAY_MS = 250L

        /** Longer pause after a busy error to avoid hammering the recognizer. */
        private const val BUSY_DELAY_MS = 1_500L
    }

    private val handler = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var isListening = false
    private var destroyed = false

    // ── Service lifecycle ─────────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        NotificationHelper.createChannels(this)
        startForeground(NOTIFICATION_ID, NotificationHelper.buildWakeWordNotification(this))
        handler.post { startRecognitionLoop() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        destroyed = true
        handler.removeCallbacksAndMessages(null)
        recognizer?.destroy()
        recognizer = null
    }

    // ── Recognition loop ──────────────────────────────────────────────────────

    private fun startRecognitionLoop() {
        if (destroyed) return
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Log.w(TAG, "Speech recognition unavailable — wake word service inactive")
            return
        }
        beginListening()
    }

    private fun beginListening() {
        if (destroyed || isListening) return
        isListening = true

        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onEvent(eventType: Int, params: Bundle?) {}

                override fun onPartialResults(partialResults: Bundle?) {
                    val partial = partialResults
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        ?.firstOrNull()
                        ?.lowercase(Locale.US) ?: return

                    // Fast-path: if a complete wake phrase is in the partial,
                    // fire immediately without waiting for final results.
                    for (phrase in WAKE_PHRASES) {
                        if (partial.contains(phrase)) {
                            val cmd = extractCommand(partial, phrase)
                            if (cmd.isNotBlank()) {
                                recognizer?.cancel()
                                isListening = false
                                broadcastWakeWord(cmd)
                                scheduleRestart(RESTART_DELAY_MS)
                                return
                            }
                        }
                    }
                }

                override fun onResults(results: Bundle?) {
                    isListening = false
                    val matches = results
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        ?.map { it.lowercase(Locale.US) }
                        ?: emptyList()
                    checkAndBroadcast(matches)
                    scheduleRestart(RESTART_DELAY_MS)
                }

                override fun onError(error: Int) {
                    isListening = false
                    val delay = when (error) {
                        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> BUSY_DELAY_MS
                        else -> RESTART_DELAY_MS
                    }
                    scheduleRestart(delay)
                }
            })
        }

        recognizer?.startListening(buildRecognizerIntent())
    }

    // ── Detection logic ───────────────────────────────────────────────────────

    /** Check a list of recognition candidates for any wake phrase. */
    internal fun checkAndBroadcast(candidates: List<String>) {
        for (candidate in candidates) {
            for (phrase in WAKE_PHRASES) {
                if (candidate.contains(phrase)) {
                    broadcastWakeWord(extractCommand(candidate, phrase))
                    return
                }
            }
        }
    }

    /**
     * Extract the command spoken after the wake phrase.
     *
     * Examples:
     *   "hey jarvis what's the weather" → "what's the weather"
     *   "hey jarvis" → ""
     */
    internal fun extractCommand(text: String, phrase: String): String {
        val idx = text.indexOf(phrase)
        if (idx < 0) return ""
        return text.substring(idx + phrase.length).trimStart(',', ' ', '.').trim()
    }

    private fun broadcastWakeWord(command: String) {
        Log.d(TAG, "Wake word detected! command='$command'")
        sendBroadcast(
            Intent(ACTION_WAKE_WORD_DETECTED).apply {
                setPackage(packageName)
                putExtra(EXTRA_COMMAND, command)
            }
        )
    }

    private fun scheduleRestart(delayMs: Long) {
        handler.postDelayed({ beginListening() }, delayMs)
    }

    // ── Intent builder ────────────────────────────────────────────────────────

    private fun buildRecognizerIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toString())
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        // Allow longer ambient listening sessions before auto-stop
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2_500L)
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 300L)
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1_500L)
    }
}
