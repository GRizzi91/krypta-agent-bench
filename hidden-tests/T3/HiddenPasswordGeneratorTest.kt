package it.gr.krypta.vault.ui.editor

import java.util.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class HiddenPasswordGeneratorTest {

    private val symbols = "!@#\$%^&*()-_=+[]{};:,.?".toSet()
    private val ambiguous = "0Oo1lI".toSet()

    @Test
    fun rejectsLengthsOutsideTheRange() {
        assertFailsWith<IllegalArgumentException> { generatePassword(7, includeSymbols = true) }
        assertFailsWith<IllegalArgumentException> { generatePassword(65, includeSymbols = false) }
    }

    @Test
    fun respectsLengthAndCharacterClasses() {
        val random = Random(42)
        for (length in listOf(8, 9, 20, 64)) {
            for (withSymbols in listOf(true, false)) {
                repeat(200) {
                    val password = generatePassword(length, withSymbols, random)
                    assertEquals(length, password.length, password)
                    assertTrue(password.any { it in 'a'..'z' }, password)
                    assertTrue(password.any { it in 'A'..'Z' }, password)
                    assertTrue(password.any { it in '0'..'9' }, password)
                    assertEquals(withSymbols, password.any { it in symbols }, password)
                    assertTrue(password.none { it in ambiguous }, password)
                    assertTrue(
                        password.all { it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it in symbols },
                        password,
                    )
                }
            }
        }
    }

    @Test
    fun theDefaultRandomIsUsable() {
        assertEquals(20, generatePassword(20, true).length)
    }
}
