package com.jarvis.os.chat

import com.jarvis.os.network.ChatRequest
import com.jarvis.os.network.JarvisApiClient
import com.jarvis.os.network.JarvisApiService

/**
 * Repository that bridges the ViewModel to the Jarvis FastAPI server.
 *
 * Accepts an optional pre-built [JarvisApiService] for dependency injection in tests.
 */
class ChatRepository(
    private val serverIp: String,
    private val api: JarvisApiService = JarvisApiClient.build(serverIp),
) {

    /**
     * Send a user message and return the Jarvis response as a [ChatMessage],
     * wrapped in a [Result] so callers handle errors without try/catch.
     */
    suspend fun sendMessage(text: String): Result<ChatMessage> = runCatching {
        val response = api.chat(ChatRequest(text.trim()))
        ChatMessage(
            role = MessageRole.JARVIS,
            text = response.text,
            adapter = response.adapter,
        )
    }
}
