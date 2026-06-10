import Foundation
import BackgroundTasks
import UserNotifications

/// Mirrors the server's unfired reminders into iOS local notifications.
/// Identifiers are "rem-<server id>" so removed/fired reminders can be
/// cancelled on the next sync.
enum ReminderSyncer {
    private static let prefix = "rem-"

    static func sync() async {
        guard let api = APIClient() else { return }
        let center = UNUserNotificationCenter.current()
        _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])

        guard let reminders = try? await api.reminders() else { return }
        let serverIDs = Set(reminders.map { prefix + $0.id })

        let pending = await center.pendingNotificationRequests()
        let stale = pending
            .map(\.identifier)
            .filter { $0.hasPrefix(prefix) && !serverIDs.contains($0) }
        center.removePendingNotificationRequests(withIdentifiers: stale)

        let alreadyScheduled = Set(pending.map(\.identifier))
        for reminder in reminders {
            let id = prefix + reminder.id
            guard !alreadyScheduled.contains(id),
                  let fireDate = reminder.fireDate, fireDate > .now else { continue }

            let content = UNMutableNotificationContent()
            content.title = "Remndrs"
            content.body = reminder.message
            content.sound = .default

            let components = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute, .second], from: fireDate)
            let trigger = UNCalendarNotificationTrigger(dateMatching: components,
                                                        repeats: false)
            try? await center.add(UNNotificationRequest(identifier: id,
                                                        content: content,
                                                        trigger: trigger))
        }
    }

    static func cancelAll() async {
        let center = UNUserNotificationCenter.current()
        let pending = await center.pendingNotificationRequests()
        let ours = pending.map(\.identifier).filter { $0.hasPrefix(prefix) }
        center.removePendingNotificationRequests(withIdentifiers: ours)
    }

    static func scheduleBackgroundRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: AppGroup.backgroundRefreshTaskID)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    static func handleBackgroundTask(_ task: BGAppRefreshTask) {
        scheduleBackgroundRefresh()
        let work = Task {
            await sync()
            task.setTaskCompleted(success: true)
        }
        task.expirationHandler = { work.cancel() }
    }
}
