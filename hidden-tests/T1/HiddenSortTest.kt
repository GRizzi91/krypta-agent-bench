package it.gr.krypta.vault.ui.list

import it.gr.krypta.vault.api.model.VaultEntry
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Instant

class HiddenSortTest {

    private fun entry(id: String, title: String, updatedAt: Long) = VaultEntry(
        id = id,
        title = title,
        codes = emptyList(),
        notes = null,
        createdAt = Instant.fromEpochMilliseconds(0),
        updatedAt = Instant.fromEpochMilliseconds(updatedAt),
    )

    private val entries = listOf(
        entry("1", "beta", 100),
        entry("2", "alpha", 400),
        entry("3", "Gamma", 200),
        entry("4", "Alpha", 300),
        entry("5", "delta", 200),
    )

    @Test
    fun nameOrderIsCaseInsensitiveAndStable() {
        val sorted = sortVaultEntries(entries, VaultSortOrder.Name)
        assertEquals(listOf("2", "4", "1", "5", "3"), sorted.map { it.id })
    }

    @Test
    fun recentlyUpdatedPutsNewestFirstAndKeepsTiesStable() {
        val sorted = sortVaultEntries(entries, VaultSortOrder.RecentlyUpdated)
        assertEquals(listOf("2", "4", "3", "5", "1"), sorted.map { it.id })
    }

    @Test
    fun sortingDoesNotChangeTheInput() {
        val before = entries.map { it.id }
        sortVaultEntries(entries, VaultSortOrder.RecentlyUpdated)
        assertEquals(before, entries.map { it.id })
    }

    @Test
    fun emptyListStaysEmpty() {
        assertEquals(emptyList<VaultEntry>(), sortVaultEntries(emptyList(), VaultSortOrder.Name))
    }
}
