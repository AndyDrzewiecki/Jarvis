package com.jarvis.os.voice

import android.media.MediaPlayer
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.URL

class TtsPlayer {
    private var mediaPlayer: MediaPlayer? = null
    private val tag = "TtsPlayer"

    /**
     * Fetch TTS audio from server and play it.
     * serverIp: e.g. "192.168.1.100:8000"
     * text: the text to speak
     */
    suspend fun play(serverIp: String, text: String, cacheDir: File) {
        stopPlayback()
        withContext(Dispatchers.IO) {
            try {
                val encoded = java.net.URLEncoder.encode(text.take(500), "UTF-8")
                val base = if (serverIp.startsWith("http")) serverIp else "http://$serverIp"
                val url = "$base/api/tts?text=$encoded"

                val tmpFile = File(cacheDir, "tts_${System.currentTimeMillis()}.mp3")
                URL(url).openStream().use { input ->
                    FileOutputStream(tmpFile).use { output ->
                        input.copyTo(output)
                    }
                }

                withContext(Dispatchers.Main) {
                    mediaPlayer = MediaPlayer().apply {
                        setDataSource(tmpFile.absolutePath)
                        prepare()
                        start()
                        setOnCompletionListener {
                            tmpFile.delete()
                            release()
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(tag, "TTS playback failed: ${e.message}")
            }
        }
    }

    fun stopPlayback() {
        mediaPlayer?.apply {
            if (isPlaying) stop()
            release()
        }
        mediaPlayer = null
    }
}
