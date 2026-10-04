package it.gr.krypta.backup.data

import it.gr.krypta.vault.model.VaultEntry
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.serialization.json.Json

class HiddenPinnedBackupTest {

    // Same configuration as the @BackupJson instance the app uses.
    private val json = Json {
        coerceInputValues = true
        explicitNulls = false
        encodeDefaults = true
        ignoreUnknownKeys = true
        isLenient = true
    }

    private fun entry(pinned: Boolean? = null): VaultEntry {
        val base = VaultEntry(
            id = "1",
            title = "Bank",
            codes = emptyList(),
            notes = null,
            createdAt = Instant.fromEpochMilliseconds(1),
            updatedAt = Instant.fromEpochMilliseconds(2),
        )
        return if (pinned == null) base else base.copy(pinned = pinned)
    }

    @Test
    fun entriesAreUnpinnedByDefault() {
        assertFalse(entry().pinned)
    }

    @Test
    fun aBackupWrittenBeforePinningRestoresUnpinnedEntries() {
        val legacy = """{"entries":[{"id":"1","title":"Bank","codes":[{"id":"c1","label":"PIN","value":"1234","category":"CardPin"}],"notes":null,"createdAtEpochMillis":1,"updatedAtEpochMillis":2}]}"""
        val payload = json.decodeFromString(BackupPayload.serializer(), legacy)
        val restored = payload.entries.single().toVaultEntry()
        assertEquals("Bank", restored.title)
        assertEquals("1234", restored.codes.single().value)
        assertFalse(restored.pinned)
    }

    @Test
    fun thePinnedFlagSurvivesABackupRoundTrip() {
        val encoded = json.encodeToString(
            BackupPayload.serializer(),
            BackupPayload(entries = listOf(entry(pinned = true).toBackupEntry())),
        )
        val decoded = json.decodeFromString(BackupPayload.serializer(), encoded)
        assertTrue(decoded.entries.single().toVaultEntry().pinned)
    }
}
