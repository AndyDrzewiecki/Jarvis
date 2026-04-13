package com.jarvis.os.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.os.device.DeviceProfile
import com.jarvis.os.ui.theme.*

@Composable
fun SettingsScreen(
    serverIp: String,
    deviceName: String,
    deviceProfile: String,
    onSave: (ip: String, name: String, profile: String) -> Unit,
) {
    var ipInput by remember { mutableStateOf(serverIp) }
    var nameInput by remember { mutableStateOf(deviceName) }
    var profileInput by remember { mutableStateOf(deviceProfile) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(ArcReactorBg)
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Settings", color = TextPrimary, fontSize = 22.sp)

        OutlinedTextField(
            value = ipInput,
            onValueChange = { ipInput = it },
            label = { Text("Server IP (e.g. 192.168.1.100:8000)", color = TextSecondary) },
            singleLine = true,
            keyboardOptions = KeyboardOptions.Default.copy(imeAction = ImeAction.Next),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = TextPrimary,
                unfocusedTextColor = TextPrimary,
                focusedBorderColor = ArcReactorGlow,
                unfocusedBorderColor = CardBorder,
            ),
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = nameInput,
            onValueChange = { nameInput = it },
            label = { Text("Device Name", color = TextSecondary) },
            singleLine = true,
            keyboardOptions = KeyboardOptions.Default.copy(imeAction = ImeAction.Next),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = TextPrimary,
                unfocusedTextColor = TextPrimary,
                focusedBorderColor = ArcReactorGlow,
                unfocusedBorderColor = CardBorder,
            ),
            modifier = Modifier.fillMaxWidth(),
        )

        Text("Device Profile", color = TextSecondary, fontSize = 14.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DeviceProfile.values().forEach { profile ->
                FilterChip(
                    selected = profileInput == profile.profileName,
                    onClick = { profileInput = profile.profileName },
                    label = { Text(profile.profileName.replaceFirstChar { it.uppercase() }) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = ArcReactorGlow,
                        selectedLabelColor = ArcReactorBg,
                        labelColor = TextSecondary,
                        containerColor = CardSurface,
                    ),
                )
            }
        }

        Spacer(modifier = Modifier.weight(1f))

        Button(
            onClick = { onSave(ipInput, nameInput, profileInput) },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = ArcReactorGlow),
        ) {
            Text("Save", color = ArcReactorBg, fontSize = 16.sp)
        }
    }
}
