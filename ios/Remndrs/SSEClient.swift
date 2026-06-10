import Foundation
import UserNotifications

extension Notification.Name {
    /// Posted whenever the server pushes an event; object is the event type string.
    static let remndrsServerEvent = Notification.Name("remndrsServerEvent")
}

/// Long-lived connection to /api/stream so the feed updates live, like the
/// web UI. Runs while the app is foregrounded; reconnects with a short
/// backoff. The server heartbeats every 30s, well inside URLSession's
/// default 60s between-bytes timeout.
@MainActor
final class SSEClient: ObservableObject {
    private var task: Task<Void, Never>?

    func start() {
        guard task == nil else { return }
        task = Task { await run() }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    private func run() async {
        while !Task.isCancelled {
            guard let credentials = CredentialsStore.load() else {
                try? await Task.sleep(for: .seconds(10))
                continue
            }
            var request = URLRequest(url: credentials.serverURL.appending(path: "api/stream"))
            request.setValue("Bearer \(credentials.token)", forHTTPHeaderField: "Authorization")
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            do {
                let (bytes, response) = try await URLSession.shared.bytes(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw URLError(.userAuthenticationRequired)
                }
                for try await line in bytes.lines {
                    guard line.hasPrefix("data: ") else { continue }
                    handle(String(line.dropFirst(6)))
                }
            } catch {
                // Dropped connection or auth problem — fall through to retry.
            }
            guard !Task.isCancelled else { break }
            try? await Task.sleep(for: .seconds(3))
        }
    }

    private func handle(_ payload: String) {
        guard let data = payload.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String,
              type != "heartbeat" else { return }

        if type == "reminder",
           let body = object["data"] as? [String: Any],
           let message = body["message"] as? String {
            postReminderNotification(id: body["id"] as? String ?? UUID().uuidString,
                                     message: message)
        }

        NotificationCenter.default.post(name: .remndrsServerEvent, object: type)
    }

    /// A reminder fired server-side while we're connected — surface it now.
    private func postReminderNotification(id: String, message: String) {
        let content = UNMutableNotificationContent()
        content.title = "Remndrs"
        content.body = message
        content.sound = .default
        let request = UNNotificationRequest(identifier: "rem-\(id)",
                                            content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
