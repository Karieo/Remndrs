import SwiftUI
import BackgroundTasks

@main
struct RemndrsApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var session = SessionModel()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: AppGroup.backgroundRefreshTaskID, using: nil
        ) { task in
            guard let refreshTask = task as? BGAppRefreshTask else { return }
            ReminderSyncer.handleBackgroundTask(refreshTask)
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .preferredColorScheme(.dark)
                .tint(Theme.accent)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                Task { await ReminderSyncer.sync() }
            } else if phase == .background {
                ReminderSyncer.scheduleBackgroundRefresh()
            }
        }
    }
}

@MainActor
final class SessionModel: ObservableObject {
    @Published var credentials: Credentials? = CredentialsStore.load()

    var api: APIClient? {
        credentials.map { APIClient(baseURL: $0.serverURL, token: $0.token) }
    }

    func signIn(_ credentials: Credentials) {
        CredentialsStore.save(credentials)
        self.credentials = credentials
    }

    func signOut() async {
        try? await api?.revokeToken()
        CredentialsStore.clear()
        credentials = nil
        await ReminderSyncer.cancelAll()
    }
}
