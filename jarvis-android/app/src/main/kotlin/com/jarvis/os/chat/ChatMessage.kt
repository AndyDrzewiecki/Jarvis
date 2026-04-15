package com.jarvis.os.chat

import java.time.Instant
import java.util.UUID

enum class MessageRole { USER, JARVIS }

/**
 * A single message in the Jarvis chat history.
 *
 * @param id        Stable identifier for list keys (UUID by default)
 * @param role      Who sent it — USER or JARVIS
 * @param text      Message body
 * @param adapter   Jarvis adapter that produced this response (empty for user messages)
 * @param timestamp When the message was created
 */
data class ChatMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: MessageRole,
    val text: String,
    val adapter: String = "",
    val timestamp: Instant = Instant.now(),
) {
    val isUser: Boolean get() = role == MessageRole.USER
    val isJarvis: Boolean get() = role == MessageRole.JARVIS
}
