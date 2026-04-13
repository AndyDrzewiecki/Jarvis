package com.jarvis.os.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val ArcReactorBg = Color(0xFF0a0a1a)
val ArcReactorGlow = Color(0xFF00bfff)
val ArcReactorRing = Color(0xFF1a3a5c)
val ArcReactorPulse = Color(0xFF4dc8ff)
val TextPrimary = Color(0xFFe8f4fd)
val TextSecondary = Color(0xFF7ab8d4)
val StatusOk = Color(0xFF00ff88)
val CardSurface = Color(0xFF111827)
val CardBorder = Color(0xFF1e3a5f)

private val JarvisDarkColors = darkColorScheme(
    primary = ArcReactorGlow,
    onPrimary = ArcReactorBg,
    secondary = ArcReactorPulse,
    onSecondary = ArcReactorBg,
    background = ArcReactorBg,
    surface = CardSurface,
    onBackground = TextPrimary,
    onSurface = TextPrimary,
    outline = CardBorder,
)

@Composable
fun JarvisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = JarvisDarkColors,
        content = content,
    )
}
