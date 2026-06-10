import Foundation

enum APIError: LocalizedError {
    case notConfigured
    case unauthorized
    case server(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: return "Open Remndrs and sign in first."
        case .unauthorized: return "Session expired — sign in again."
        case .server(let message): return message
        }
    }
}

struct APIClient {
    let baseURL: URL
    let token: String

    init?(credentials: Credentials? = CredentialsStore.load()) {
        guard let credentials else { return nil }
        baseURL = credentials.serverURL
        token = credentials.token
    }

    init(baseURL: URL, token: String) {
        self.baseURL = baseURL
        self.token = token
    }

    // MARK: - Auth

    static func obtainToken(server: URL, login: String, password: String,
                            deviceName: String) async throws -> TokenResponse {
        var request = URLRequest(url: server.appending(path: "api/auth/token"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "login": login, "password": password, "device_name": deviceName,
        ])
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.server("Bad response") }
        if http.statusCode == 401 { throw APIError.server("Invalid name or password") }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.server("Server error (\(http.statusCode))")
        }
        return try JSONDecoder().decode(TokenResponse.self, from: data)
    }

    func revokeToken() async throws {
        _ = try await send(path: "api/auth/token", method: "DELETE")
    }

    // MARK: - Notes

    func notes(feed: String? = nil, tag: String? = nil, search: String? = nil,
               source: String? = nil) async throws -> [Note] {
        var items: [URLQueryItem] = []
        if let feed { items.append(.init(name: "feed", value: feed)) }
        if let tag { items.append(.init(name: "tag", value: tag)) }
        if let search, !search.isEmpty { items.append(.init(name: "search", value: search)) }
        if let source { items.append(.init(name: "source", value: source)) }
        let data = try await send(path: "api/notes", query: items)
        return try JSONDecoder().decode([Note].self, from: data)
    }

    func createNote(content: String, tags: [String], feed: String,
                    type: String = "note", todos: [TodoItem] = []) async throws -> Note {
        var body: [String: Any] = [
            "content": content, "tags": tags, "feed": feed,
            "type": type, "source": "ios",
        ]
        if !todos.isEmpty {
            body["todos"] = todos.map { ["text": $0.text, "checked": $0.checked] }
        }
        let data = try await send(path: "api/notes", method: "POST", json: body)
        return try JSONDecoder().decode(Note.self, from: data)
    }

    func updateNote(id: String, fields: [String: Any]) async throws -> Note {
        let data = try await send(path: "api/notes/\(id)", method: "PATCH", json: fields)
        return try JSONDecoder().decode(Note.self, from: data)
    }

    func deleteNote(id: String) async throws {
        _ = try await send(path: "api/notes/\(id)", method: "DELETE")
    }

    func users() async throws -> [Person] {
        try JSONDecoder().decode([Person].self, from: try await send(path: "api/users"))
    }

    func shareNote(id: String, recipientID: String, message: String?) async throws -> Note {
        var body: [String: Any] = ["recipient_id": recipientID]
        if let message, !message.isEmpty { body["message"] = message }
        let data = try await send(path: "api/notes/\(id)/share", method: "POST", json: body)
        return try JSONDecoder().decode(Note.self, from: data)
    }

    func replyToNote(id: String, text: String) async throws {
        _ = try await send(path: "api/notes/\(id)/replies", method: "POST",
                           json: ["text": text])
    }

    func sendNote(id: String, channel: String, to: String?) async throws {
        var body: [String: Any] = ["channel": channel]
        if let to, !to.isEmpty { body["to"] = to }
        _ = try await send(path: "api/notes/\(id)/send", method: "POST", json: body)
    }

    func noteToEvent(id: String, calendarName: String, startAt: Date,
                     endAt: Date, allDay: Bool) async throws {
        _ = try await send(path: "api/notes/\(id)/to-event", method: "POST", json: [
            "calendar_name": calendarName,
            "start_at": RemndrsDate.format(startAt),
            "end_at": RemndrsDate.format(endAt),
            "all_day": allDay,
        ])
    }

    // MARK: - Tags / reminders / calendar

    func tags() async throws -> [Tag] {
        try JSONDecoder().decode([Tag].self, from: try await send(path: "api/tags"))
    }

    func reminders() async throws -> [Reminder] {
        try JSONDecoder().decode([Reminder].self, from: try await send(path: "api/reminders"))
    }

    func calendarEvents() async throws -> [CalendarEvent] {
        try JSONDecoder().decode([CalendarEvent].self,
                                 from: try await send(path: "api/calendar/events"))
    }

    func calendarPrefs() async throws -> [CalendarPref] {
        try JSONDecoder().decode([CalendarPref].self,
                                 from: try await send(path: "api/calendar/prefs"))
    }

    func linkPreview(url: String) async throws -> LinkPreview {
        let data = try await send(path: "api/preview",
                                  query: [.init(name: "url", value: url)])
        return try JSONDecoder().decode(LinkPreview.self, from: data)
    }

    // MARK: - Uploads

    func uploadAttachment(noteID: String, data: Data, filename: String,
                          mimeType: String) async throws -> AttachmentUpload {
        var body = MultipartBody()
        body.addField(name: "note_id", value: noteID)
        body.addFile(name: "file", filename: filename, mimeType: mimeType, data: data)
        let response = try await send(path: "api/attachments", method: "POST", multipart: body)
        return try JSONDecoder().decode(AttachmentUpload.self, from: response)
    }

    func transcribe(audioURL: URL) async throws -> Transcription {
        let audioData = try Data(contentsOf: audioURL)
        var body = MultipartBody()
        body.addFile(name: "audio", filename: "memo.m4a", mimeType: "audio/mp4", data: audioData)
        let response = try await send(path: "api/voice/transcribe", method: "POST",
                                      multipart: body, timeout: 120)
        return try JSONDecoder().decode(Transcription.self, from: response)
    }

    // MARK: - Core request

    @discardableResult
    private func send(path: String, method: String = "GET",
                      query: [URLQueryItem] = [], json: [String: Any]? = nil,
                      multipart: MultipartBody? = nil,
                      timeout: TimeInterval = 30) async throws -> Data {
        var url = baseURL.appending(path: path)
        if !query.isEmpty { url.append(queryItems: query) }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let json {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: json)
        }
        if let multipart {
            request.setValue(multipart.contentType, forHTTPHeaderField: "Content-Type")
            request.httpBody = multipart.data
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.server("Bad response") }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else {
            let message = (try? JSONDecoder().decode([String: String].self, from: data))?["error"]
            throw APIError.server(message ?? "Server error (\(http.statusCode))")
        }
        return data
    }
}

struct MultipartBody {
    let boundary = "remndrs-\(UUID().uuidString)"
    private var parts = Data()

    var contentType: String { "multipart/form-data; boundary=\(boundary)" }

    var data: Data {
        var d = parts
        d.append(Data("--\(boundary)--\r\n".utf8))
        return d
    }

    mutating func addField(name: String, value: String) {
        parts.append(Data("--\(boundary)\r\n".utf8))
        parts.append(Data("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".utf8))
        parts.append(Data("\(value)\r\n".utf8))
    }

    mutating func addFile(name: String, filename: String, mimeType: String, data fileData: Data) {
        parts.append(Data("--\(boundary)\r\n".utf8))
        parts.append(Data(
            "Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".utf8))
        parts.append(Data("Content-Type: \(mimeType)\r\n\r\n".utf8))
        parts.append(fileData)
        parts.append(Data("\r\n".utf8))
    }
}
