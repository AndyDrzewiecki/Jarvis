package com.jarvis.os.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.os.ui.theme.*

data class NotebookEntry(
    val id: String,
    val title: String,
    val content: String,
    val category: String,
    val deviceId: String,
    val createdAt: String,
)

@Composable
fun NotebookScreen(
    entries: List<NotebookEntry>,
    onSearch: (String) -> Unit,
    onBack: () -> Unit,
) {
    var searchQuery by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(ArcReactorBg)
            .padding(16.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Notebook", color = TextPrimary, fontSize = 22.sp)
            TextButton(onClick = onBack) {
                Text("Back", color = TextSecondary)
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = searchQuery,
            onValueChange = {
                searchQuery = it
                onSearch(it)
            },
            placeholder = { Text("Search…", color = TextSecondary) },
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = TextPrimary,
                unfocusedTextColor = TextPrimary,
                focusedBorderColor = ArcReactorGlow,
                unfocusedBorderColor = CardBorder,
            ),
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(modifier = Modifier.height(8.dp))

        if (entries.isEmpty()) {
            Text(
                "No items saved yet. Ask Jarvis something and tap Save to Notebook.",
                color = TextSecondary,
                fontSize = 14.sp,
            )
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(entries) { entry ->
                    NotebookEntryCard(entry)
                }
            }
        }
    }
}

@Composable
fun NotebookEntryCard(entry: NotebookEntry) {
    Card(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = CardSurface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            if (entry.title.isNotBlank()) {
                Text(entry.title, color = TextPrimary, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
            }
            Text(
                entry.content.take(120) + if (entry.content.length > 120) "…" else "",
                color = TextSecondary,
                fontSize = 13.sp,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(entry.category, color = ArcReactorGlow, fontSize = 11.sp)
                Text(entry.deviceId, color = TextSecondary, fontSize = 11.sp)
            }
        }
    }
}
