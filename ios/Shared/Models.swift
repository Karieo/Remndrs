import Foundation

struct Note: Codable, Identifiable, Hashable {
    let id: String
    let userId: String
    let userName: String?
    var feed: String
    var type: String
    var content: String
    let source: String
    var pinned: Bool
    // Optional so decoding still works against servers from before archiving.
    var archived: Bool?
    // When true, the card shows only title/date/tags until revealed. Optional
    // so older servers (no `hidden` field) still decode.
    var hidden: Bool?
    // Custom accent color (hex like "#60a5fa"); overrides the tag accent. Optional.
    var color: String?
    let createdAt: String
    let updatedAt: String
    var tags: [TagRef]
    var todos: [TodoItem]
    var attachments: [AttachmentRef]
    var share: ShareInfo?
    var replies: [Reply]

    enum CodingKeys: String, CodingKey {
        case id, feed, type, content, source, pinned, archived, hidden, color, tags, todos, attachments
        case share, replies
        case userId = "user_id"
        case userName = "user_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var createdDate: Date? { RemndrsDate.parse(createdAt) }
    var isArchived: Bool { archived ?? false }
    var isHidden: Bool { hidden ?? false }
    /// First line of the content — the de-facto title shown when hidden.
    var titleLine: String {
        content.split(separator: "\n", maxSplits: 1).first.map(String.init) ?? "(untitled)"
    }
}

struct TagRef: Codable, Hashable {
    let name: String
    let color: String
}

struct ShareInfo: Codable, Hashable {
    let senderId: String
    let senderName: String
    let recipientId: String
    let recipientName: String
    let message: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case message
        case senderId = "sender_id"
        case senderName = "sender_name"
        case recipientId = "recipient_id"
        case recipientName = "recipient_name"
        case createdAt = "created_at"
    }
}

struct Reply: Codable, Hashable, Identifiable {
    let id: String
    let userId: String
    let userName: String
    let text: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, text
        case userId = "user_id"
        case userName = "user_name"
        case createdAt = "created_at"
    }
}

struct Person: Codable, Identifiable, Hashable {
    let id: String
    let name: String
}

struct Tag: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let color: String
    let count: Int
}

struct TodoItem: Codable, Hashable {
    let id: String?
    var text: String
    var checked: Bool
    /// Optional per-item due date (naive local ISO). Optional so older servers
    /// and notes without due dates still decode.
    var dueAt: String?
    /// Sub-task nesting level (0 = top). Optional so older servers decode.
    var indent: Int?

    enum CodingKeys: String, CodingKey {
        case id, text, checked, indent
        case dueAt = "due_at"
    }

    var dueDate: Date? {
        guard let d = dueAt, !d.isEmpty else { return nil }
        return RemndrsDate.parse(d)
    }
    var isOverdue: Bool { !checked && (dueDate.map { $0 < Date() } ?? false) }
}

struct AttachmentRef: Codable, Hashable {
    let id: String
    let originalFilename: String
    let savedFilename: String
    let mimeType: String?

    enum CodingKeys: String, CodingKey {
        case id
        case originalFilename = "original_filename"
        case savedFilename = "saved_filename"
        case mimeType = "mime_type"
    }
}

struct Reminder: Codable, Identifiable, Hashable {
    let id: String
    let message: String
    let fireAt: String
    /// iCal RRULE when the reminder repeats (e.g. "FREQ=WEEKLY;BYDAY=MO"),
    /// nil for a one-off. Optional so older servers still decode.
    var recurrence: String?

    enum CodingKeys: String, CodingKey {
        case id, message, recurrence
        case fireAt = "fire_at"
    }

    var fireDate: Date? { RemndrsDate.parse(fireAt) }
    var repeats: Bool { !(recurrence ?? "").isEmpty }
}

struct CalendarEvent: Codable, Identifiable, Hashable {
    let id: String
    let calendarName: String
    let feed: String
    let title: String
    let location: String?
    let startAt: String
    let endAt: String
    let allDay: Int
    let deleted: Int

    enum CodingKeys: String, CodingKey {
        case id, feed, title, location, deleted
        case calendarName = "calendar_name"
        case startAt = "start_at"
        case endAt = "end_at"
        case allDay = "all_day"
    }

    var startDate: Date? { RemndrsDate.parse(startAt) }
    var isAllDay: Bool { allDay == 1 }
    var isOrphaned: Bool { deleted == 1 }
}

struct CalendarPref: Codable, Hashable {
    let calendarName: String
    let enabled: Bool
    let feed: String

    enum CodingKeys: String, CodingKey {
        case enabled, feed
        case calendarName = "calendar_name"
    }
}

struct Transcription: Codable {
    let transcript: String
    let tags: [String]
}

struct AttachmentUpload: Codable {
    let savedFilename: String
    let markdown: String

    enum CodingKeys: String, CodingKey {
        case markdown
        case savedFilename = "saved_filename"
    }
}

struct TokenResponse: Codable {
    let token: String
    let user: UserInfo
}

struct UserInfo: Codable {
    let id: String
    let name: String
    let role: String
}

struct LinkPreview: Codable {
    let url: String?
    let title: String?
    let description: String?
    let siteName: String?

    enum CodingKeys: String, CodingKey {
        case url, title, description
        case siteName = "site_name"
    }
}

/// The server stores naive local ISO timestamps (Mac and phone are assumed
/// to share a timezone).
enum RemndrsDate {
    private static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        return f
    }()

    static func parse(_ s: String) -> Date? {
        formatter.date(from: String(s.prefix(19)))
    }

    static func format(_ d: Date) -> String {
        formatter.string(from: d)
    }
}
