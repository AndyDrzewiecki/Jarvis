package com.jarvis.os.chat

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.os.ui.theme.*
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val TIME_FMT = DateTimeFormatter.ofPattern("h:mm a").withZone(ZoneId.systemDefault())

/**
 * Full chat screen — mirrors the web dashboard's chat panel.
 *
 * Shows a scrolling message history, a text input, and a voice button.
 * Wire the voice button to the same VoiceManager used on HomeScreen.
 */
@Composable
fun ChatScreen(
    uiState: ChatUiState,
    isListening: Boolean,
    voiceTranscript: String,
    onSendMessage: (String) -> Unit,
    onVoiceButtonClick: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()
    val messages = uiState.messages

    // Auto-scroll to bottom when new messages arrive
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(ArcReactorBg),
    ) {
        // ── Top bar ──────────────────────────────────────────────────────────
        ChatTopBar(onBack = onBack)

        // ── Message list ─────────────────────────────────────────────────────
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (messages.isEmpty()) {
                item { EmptyState() }
            }
            items(messages, key = { it.id }) { msg ->
                MessageBubble(message = msg)
            }
            // Live transcription while listening
            if (isListening && voiceTranscript.isNotBlank()) {
                item {
                    PartialTranscriptBubble(text = voiceTranscript)
                }
            }
            // Loading indicator while waiting for Jarvis
            if (uiState.isLoading) {
                item { JarvisThinkingBubble() }
            }
        }

        // ── Error banner ──────────────────────────────────────────────────────
        AnimatedVisibility(
            visible = uiState.error != null,
            enter = fadeIn(),
            exit = fadeOut(),
        ) {
            uiState.error?.let { err ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFF4a0000))
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(err, color = Color(0xFFff6b6b), fontSize = 12.sp, modifier = Modifier.weight(1f))
                    IconButton(onClick = { /* clearError via parent */ }, modifier = Modifier.size(24.dp)) {
                        Icon(Icons.Default.Clear, contentDescription = "Dismiss", tint = Color(0xFFff6b6b))
                    }
                }
            }
        }

        // ── Input row ────────────────────────────────────────────────────────
        ChatInputRow(
            isListening = isListening,
            onSend = onSendMessage,
            onVoice = onVoiceButtonClick,
        )
    }
}

@Composable
private fun ChatTopBar(onBack: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(CardSurface)
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = ArcReactorGlow)
        }
        Text(
            text = "JARVIS",
            color = ArcReactorGlow,
            fontSize = 18.sp,
            letterSpacing = 4.sp,
            modifier = Modifier.weight(1f),
            textAlign = TextAlign.Center,
        )
        // Spacer to balance the back button
        Spacer(Modifier.size(48.dp))
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isUser = message.isUser
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Column(
            horizontalAlignment = if (isUser) Alignment.End else Alignment.Start,
            modifier = Modifier.widthIn(max = 300.dp),
        ) {
            Surface(
                shape = RoundedCornerShape(
                    topStart = 16.dp,
                    topEnd = 16.dp,
                    bottomStart = if (isUser) 16.dp else 4.dp,
                    bottomEnd = if (isUser) 4.dp else 16.dp,
                ),
                color = if (isUser) ArcReactorRing else CardSurface,
                tonalElevation = 1.dp,
            ) {
                Text(
                    text = message.text,
                    color = if (isUser) ArcReactorPulse else TextPrimary,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                )
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(top = 2.dp),
            ) {
                if (!isUser && message.adapter.isNotBlank()) {
                    Text(
                        text = message.adapter,
                        color = TextSecondary.copy(alpha = 0.7f),
                        fontSize = 10.sp,
                    )
                    Text("·", color = TextSecondary.copy(alpha = 0.4f), fontSize = 10.sp)
                }
                Text(
                    text = TIME_FMT.format(message.timestamp),
                    color = TextSecondary.copy(alpha = 0.5f),
                    fontSize = 10.sp,
                )
            }
        }
    }
}

@Composable
private fun PartialTranscriptBubble(text: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Surface(
            shape = RoundedCornerShape(16.dp, 16.dp, 4.dp, 16.dp),
            color = ArcReactorRing.copy(alpha = 0.5f),
        ) {
            Text(
                text = "$text…",
                color = ArcReactorPulse.copy(alpha = 0.7f),
                fontSize = 14.sp,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            )
        }
    }
}

@Composable
private fun JarvisThinkingBubble() {
    val infiniteTransition = rememberInfiniteTransition(label = "thinking")
    val alpha by infiniteTransition.animateFloat(
        initialValue = 0.3f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(700, easing = EaseInOut), RepeatMode.Reverse),
        label = "alpha",
    )
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
        Surface(
            shape = RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp),
            color = CardSurface,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                repeat(3) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(CircleShape)
                            .background(ArcReactorGlow.copy(alpha = alpha))
                    )
                }
            }
        }
    }
}

@Composable
private fun EmptyState() {
    Box(modifier = Modifier.fillMaxWidth().padding(vertical = 80.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("J A R V I S", color = ArcReactorGlow.copy(alpha = 0.4f), fontSize = 28.sp, letterSpacing = 8.sp)
            Text("Ready, Sir.", color = TextSecondary.copy(alpha = 0.5f), fontSize = 14.sp)
        }
    }
}

@Composable
private fun ChatInputRow(
    isListening: Boolean,
    onSend: (String) -> Unit,
    onVoice: () -> Unit,
) {
    var inputText by remember { mutableStateOf("") }

    Surface(
        color = CardSurface,
        tonalElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // Voice button
            IconButton(
                onClick = onVoice,
                modifier = Modifier
                    .size(40.dp)
                    .background(
                        color = if (isListening) ArcReactorGlow.copy(alpha = 0.2f) else Color.Transparent,
                        shape = CircleShape,
                    ),
            ) {
                Icon(
                    imageVector = Icons.Default.Mic,
                    contentDescription = if (isListening) "Stop listening" else "Start listening",
                    tint = if (isListening) ArcReactorGlow else TextSecondary,
                )
            }

            // Text input
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Ask Jarvis…", color = TextSecondary.copy(alpha = 0.5f), fontSize = 14.sp) },
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = ArcReactorGlow,
                    unfocusedBorderColor = CardBorder,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                    cursorColor = ArcReactorGlow,
                ),
                textStyle = LocalTextStyle.current.copy(fontSize = 14.sp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = {
                    if (inputText.isNotBlank()) {
                        onSend(inputText)
                        inputText = ""
                    }
                }),
            )

            // Send button
            IconButton(
                onClick = {
                    if (inputText.isNotBlank()) {
                        onSend(inputText)
                        inputText = ""
                    }
                },
                enabled = inputText.isNotBlank(),
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send",
                    tint = if (inputText.isNotBlank()) ArcReactorGlow else TextSecondary.copy(alpha = 0.4f),
                )
            }
        }
    }
}
