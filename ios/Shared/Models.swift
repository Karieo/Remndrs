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
    let createdAt: String
    let updatedAt: String
    var tags: [TagRef]
    var todos: [TodoItem]
    var attachments: [AttachmentRef]

    enum CodingKeys: String, CodingKey {
        case id, feed, type, content, source, pinned, tags, todos, attachments
        case userId = "user_id"
        case userName = "user_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var createdDate: Date? { RemndrsDate.parse(createdAt) }
}

struct TagRef: Codable, Hashable {
    let name: String
    let color: String
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

    enum CodingKeys: String, CodingKey { case id, text, checked }
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

    enum CodingKeys: String, CodingKey {
        case id, message
        case fireAt = "fire_at"
    }

    var fireDate: Date? { RemndrsDate.parse(fireAt) }
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
