package com.jarvis.os.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

class ChatViewModel(
    private val repository: ChatRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    /**
     * Send a user message. Appends it immediately, then awaits the Jarvis response.
     * Wake-word commands can be injected here directly.
     */
    fun sendMessage(text: String) {
        if (text.isBlank()) return

        val userMsg = ChatMessage(role = MessageRole.USER, text = text.trim())
        _uiState.update { it.copy(messages = it.messages + userMsg, isLoading = true, error = null) }

        viewModelScope.launch {
            repository.sendMessage(text.trim()).fold(
                onSuccess = { response ->
                    _uiState.update { it.copy(messages = it.messages + response, isLoading = false) }
                },
                onFailure = { e ->
                    _uiState.update {
                        it.copy(isLoading = false, error = "Connection error: ${e.message}")
                    }
                },
            )
        }
    }

    /** Ingest a server-pushed alert as a Jarvis message (from WebSocket). */
    fun injectPushMessage(text: String, adapter: String = "push") {
        val msg = ChatMessage(role = MessageRole.JARVIS, text = text, adapter = adapter)
        _uiState.update { it.copy(messages = it.messages + msg) }
    }

    fun clearError() = _uiState.update { it.copy(error = null) }

    fun clearHistory() = _uiState.update { it.copy(messages = emptyList()) }

    // ── Factory ───────────────────────────────────────────────────────────────

    class Factory(private val repository: ChatRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            ChatViewModel(repository) as T
    }
}
