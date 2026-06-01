package com.hanstock.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Hanstock Sleek Dark Theme Colors
val DeepNavy = Color(0xFF0A0F1D)
val CharcoalNavy = Color(0xFF121829)
val EmeraldGreen = Color(0xFF00E676)
val MutedText = Color(0xFF8A99AD)
val White = Color(0xFFFFFFFF)

private val DarkColorScheme = darkColorScheme(
    primary = EmeraldGreen,
    secondary = CharcoalNavy,
    background = DeepNavy,
    surface = CharcoalNavy,
    onPrimary = DeepNavy,
    onSecondary = White,
    onBackground = White,
    onSurface = White
)

@Composable
fun HanstockTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    // We enforce dark theme for Hanstock as requested by the design aesthetics
    val colorScheme = DarkColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        content = content
    )
}
