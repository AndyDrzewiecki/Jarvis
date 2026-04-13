package com.jarvis.os.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.os.ui.theme.*

data class JarvisResponse(
    val text: String,
    val adapter: String,
)

@Composable
fun HomeScreen(
    isListening: Boolean,
    transcript: String,
    lastResponse: JarvisResponse?,
    deviceName: String,
    onVoiceButtonClick: () -> Unit,
    onSaveToNotebook: (String) -> Unit,
    onSettingsClick: () -> Unit,
    onNotebookClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(ArcReactorBg)
    ) {
        // Top status strip
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .align(Alignment.TopCenter),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = deviceName,
                color = TextSecondary,
                fontSize = 12.sp,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onNotebookClick) {
                    Text("Notebook", color = TextSecondary, fontSize = 12.sp)
                }
                TextButton(onClick = onSettingsClick) {
                    Text("Settings", color = TextSecondary, fontSize = 12.sp)
                }
            }
        }

        // Center: arc reactor + voice button
        Column(
            modifier = Modifier.align(Alignment.Center),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            ArcReactorButton(
                isListening = isListening,
                onClick = onVoiceButtonClick,
            )

            if (transcript.isNotBlank()) {
                Text(
                    text = transcript,
                    color = TextSecondary,
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(horizontal = 32.dp),
                )
            }
        }

        // Response card at bottom
        if (lastResponse != null) {
            ResponseCard(
                response = lastResponse,
                onSaveToNotebook = onSaveToNotebook,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(16.dp),
            )
        }
    }
}

@Composable
fun ArcReactorButton(
    isListening: Boolean,
    onClick: () -> Unit,
) {
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = if (isListening) 1f else 0.6f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = EaseInOut),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulseAlpha",
    )

    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(160.dp)
            .clip(CircleShape)
            .clickable { onClick() },
    ) {
        Canvas(modifier = Modifier.size(160.dp)) {
            val center = Offset(size.width / 2, size.height / 2)
            val outerRadius = size.minDimension / 2 - 4.dp.toPx()
            val innerRadius = outerRadius * 0.6f

            // Outer glow ring
            drawCircle(
                color = ArcReactorGlow.copy(alpha = pulseAlpha * 0.3f),
                radius = outerRadius + 8.dp.toPx(),
                center = center,
            )
            // Outer ring stroke
            drawCircle(
                color = ArcReactorRing,
                radius = outerRadius,
                center = center,
                style = Stroke(width = 2.dp.toPx()),
            )
            // Inner glow
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(
                        ArcReactorGlow.copy(alpha = pulseAlpha),
                        ArcReactorBg.copy(alpha = 0.8f),
                    ),
                    center = center,
                    radius = innerRadius,
                ),
                radius = innerRadius,
                center = center,
            )
            // Core dot
            drawCircle(
                color = ArcReactorPulse.copy(alpha = pulseAlpha),
                radius = 12.dp.toPx(),
                center = center,
            )
        }
    }
}

@Composable
fun ResponseCard(
    response: JarvisResponse,
    onSaveToNotebook: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = CardSurface),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = response.text,
                color = TextPrimary,
                fontSize = 15.sp,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = response.adapter,
                    color = TextSecondary,
                    fontSize = 11.sp,
                )
                TextButton(onClick = { onSaveToNotebook(response.text) }) {
                    Text("Save to Notebook", color = ArcReactorGlow, fontSize = 12.sp)
                }
            }
        }
    }
}
