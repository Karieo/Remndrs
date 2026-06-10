import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var session: SessionModel
    @State private var syncing = false
    @State private var lastSync: Date?

    var body: some View {
        List {
            Section {
                HStack(spacing: 12) {
                    Avatar(name: session.credentials?.userName ?? "?", size: 44)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(session.credentials?.userName ?? "—")
                            .font(Theme.body(16, weight: .semibold))
                            .foregroundStyle(Theme.text)
                        Text(session.credentials?.serverURL.host() ?? "")
                            .font(Theme.mono(11))
                            .foregroundStyle(Theme.textMuted)
                    }
                }
                .listRowBackground(Theme.surface)
            }

            Section {
                Button {
                    Task {
                        syncing = true
                        await ReminderSyncer.sync()
                        lastSync = .now
                        syncing = false
                    }
                } label: {
                    HStack {
                        Text(syncing ? "Syncing…" : "Sync reminders now")
                            .font(Theme.body(15))
                            .foregroundStyle(Theme.text)
                        Spacer()
                        if let lastSync {
                            Text(lastSync.formatted(date: .omitted, time: .shortened))
                                .font(Theme.mono(11))
                                .foregroundStyle(Theme.textMuted)
                        }
                    }
                }
                .listRowBackground(Theme.surface)
            } footer: {
                Text("Reminders also sync automatically when the app opens "
                     + "and periodically in the background.")
                    .font(Theme.body(12))
                    .foregroundStyle(Theme.textMuted)
            }

            Section {
                Button(role: .destructive) {
                    Task { await session.signOut() }
                } label: {
                    Text("Sign out")
                        .font(Theme.body(15))
                }
                .listRowBackground(Theme.surface)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.bg)
        .navigationTitle("Settings")
        .toolbar(.visible, for: .navigationBar)
    }
}
