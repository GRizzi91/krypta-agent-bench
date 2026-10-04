Restructure the Android app in `/tmp/krypta-bench/arms/C/Krypta` so that an AI coding agent can change it with fewer files, fewer hops and less reading, while the app keeps behaving exactly as it does now.

Context. Krypta is a password vault (Kotlin, Jetpack Compose, Hilt, Room + SQLCipher, Glance widget, Google Drive backup, Play Billing). It builds against shared libraries in `../tools` (grizzi design system, MVI base classes, navigation helpers, `hilt-binder`), consumed from source through a Gradle composite build. Today it has 10 Gradle modules: `app`, `appconfig`, `backup`, `billing`, `billing-api`, `security`, `theme`, `vault`, `vault-api`, `widget`. A single operation such as "read one entry" crosses an interface in `vault-api`, an implementation in `vault/domain`, a repository interface and its only implementation; each screen is split into five files.

This is a dedicated experiment copy. The workspace instructions you may have loaded (the long `CLAUDE.md` describing `-api` modules, use-case interfaces, `@InstallBinding` and the five-files-per-screen layout) describe the architecture this task removes: for this task they do not apply. The design-system-first rule for UI still applies.

Target structure:
1. Three Gradle modules: `app` (every feature: vault, backup, billing, widget, app shell, config), `security` (cryptography, unchanged unless a dependency forces it) and `theme` (unchanged). Delete `appconfig`, `backup`, `billing`, `billing-api`, `vault`, `vault-api`, `widget` after moving their code, resources, manifest entries, ProGuard/R8 rules, dependencies and test dependencies into `app`. Update `settings.gradle.kts`.
2. Keep the Kotlin package of every file that survives (for example `it.gr.krypta.vault.ui.list`, `it.gr.krypta.vault.ui.editor`, `it.gr.krypta.backup.data`). Shared models move from `it.gr.krypta.vault.api.model` to `it.gr.krypta.vault.model`. Packages that only held removed layers (`...api.usecase`, `...domain`) disappear.
3. No layer that only forwards a call. Delete use-case interfaces and implementations that just delegate; callers use the class that does the work. An interface stays only if it has two or more real implementations or a framework requires it. A repository with one implementation becomes a concrete class.
4. No `@InstallBinding` / `hilt-binder`: concrete classes with `@Inject` constructors need no binding; use a plain Hilt `@Binds` or `@Provides` only where an interface or a third-party type requires it.
5. Two files per screen: `XScreen.kt` (route, navigation entry, composables, previews) and `XViewModel.kt` (state, events, ViewModel). Merge small data-layer files of one feature where they always change together (for example entity, DAO, database and migrations in one file).
6. Keep the grizzi libraries the app uses (design system, `StateViewModel`, `EventChannel`, `@NavigationNode` routes, `navigateFrom`, transitions): this task changes structure, not frameworks.

Behavior that must not change:
- Every screen, flow, string (English `values/`, Italian `values-it/`), icon and resource prefix.
- Everything stored on users' devices: database file `krypta_vault.db`, its schema version (2), tables, columns and the 1->2 migration; DataStore names (`krypta_security`, `krypta_vault_labels`, `krypta_backup`, `krypta_billing`); Keystore alias `krypta_vault_key_wrapping`; backup file `krypta_backup.json` and its JSON format (field names, envelope version, restore of version 1 backups); WorkManager unique work names; clipboard label.
- Fully qualified names of classes referenced by the manifest or by other apps (activities, the widget receiver `it.gr.krypta.widget.KryptaWidgetReceiver`, workers, services), the application id, flavors, BuildConfig fields, deep link schemes, R8 keep rules.
- Security behavior: FLAG_SECURE, the signature check, the auto-lock after 30 seconds, biometric requirements, zeroing of key arrays.

How to work:
- Do not modify `../tools` or `../shared-files`.
- Move in small steps and build after each one: `./gradlew assembleDevDebug -q --console=plain` from the Krypta directory (one Gradle build at a time; the machine has little memory).
- When the structure is done, run `./gradlew assembleDevDebug lintDevDebug --console=plain` and fix every error.
- Keep the code style: explicit imports, no `!!`, no unsafe casts, lines up to 120 characters, existing comments where they still apply.

When you finish, reply with: the final module and package layout (a short tree), the number of Kotlin files before and after, and every place where behavior might differ from the original, however small. If something cannot be done without changing behavior, leave it as it was and say so.
