import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

struct ComposerView: View {
    @EnvironmentObject private var session: SessionModel
    @Environment(\.dismiss) private var dismiss

    @State private var mode = "note"
    @State private var text = ""
    @State private var feed = "private"
    @State private var photoItems: [PhotosPickerItem] = []
    @State private var fileURLs: [URL] = []
    @State private var showFileImporter = false
    @State private var saving = false
    @State private var errorMessage: String?
    @FocusState private var focused: Bool

    /// Prefill support (share extension paths reuse ShareComposeView instead).
    var initialText: String = ""
    /// When set, the composer edits this note (PATCH) instead of creating one.
    var editingNote: Note?

    var body: some View {
        VStack(spacing: 0) {
            header
            BrandSegmentedControl(selection: $mode,
                                  options: [("note", "Note"), ("todo", "To-Do")])
                .padding(.horizontal, 18)
                .padding(.top, 10)

            editor

            tagPreviewRow

            footer
        }
        .background(Theme.bg)
        .preferredColorScheme(.dark)
        .onAppear {
            if let note = editingNote {
                mode = note.type == "todo" ? "todo" : "note"
                feed = note.feed
                var lines: [String]
                if note.type == "todo" {
                    lines = [note.content.components(separatedBy: "\n").first ?? note.content]
                    lines += note.todos.map { "\($0.checked ? "[x] " : "")\($0.text)" }
                } else {
                    lines = [note.content]
                }
                var prefill = lines.joined(separator: "\n")
                if !note.tags.isEmpty {
                    prefill += "\n\n" + note.tags.map { "#\($0.name.lowercased())" }
                        .joined(separator: " ")
                }
                text = prefill
            } else {
                text = initialText
            }
            focused = true
        }
        .fileImporter(isPresented: $showFileImporter,
                      allowedContentTypes: importTypes,
                      allowsMultipleSelection: true) { result in
            if case .success(let urls) = result {
                fileURLs.append(contentsOf: urls)
            }
        }
        .alert("Couldn't save", isPresented: .init(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } })) {
            Button("OK") {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private var header: some View {
        HStack {
            Button("Cancel") { dismiss() }
                .font(Theme.body(15))
                .foregroundStyle(Theme.textMuted)
            Spacer()
            Text(editingNote != nil ? "Edit \(mode == "todo" ? "To-Do" : "Note")"
                 : (mode == "todo" ? "New To-Do" : "New Note"))
                .font(Theme.display(17))
                .foregroundStyle(Theme.text)
            Spacer()
            Button {
                Task { await save() }
            } label: {
                Text(saving ? "Saving…" : "Save")
                    .font(Theme.mono(13, weight: .semibold))
                    .foregroundStyle(Theme.bg)
                    .padding(.vertical, 7)
                    .padding(.horizontal, 15)
                    .background(Theme.accent, in: Capsule())
            }
            .disabled(saving || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(.horizontal, 18)
        .padding(.top, 16)
    }

    private var editor: some View {
        ZStack(alignment: .topLeading) {
            TextEditor(text: $text)
                .focused($focused)
                .font(Theme.body(16))
                .lineSpacing(5)
                .foregroundStyle(Theme.text)
                .scrollContentBackground(.hidden)
                .padding(.horizontal, 14)
                .padding(.top, 8)
            if text.isEmpty {
                Text(mode == "todo"
                     ? "First line is the title; each line after is a task."
                     : "#tags are pulled out automatically.")
                    .font(Theme.body(16, italic: true))
                    .foregroundStyle(Theme.textFaint)
                    .padding(.horizontal, 19)
                    .padding(.top, 16)
                    .allowsHitTesting(false)
            }
        }
        .frame(maxHeight: .infinity)
    }

    private var tagPreviewRow: some View {
        HStack(spacing: 7) {
            Text("TAGS")
                .font(Theme.mono(9.5)).kerning(0.5)
                .foregroundStyle(Theme.textFaint)
            if extractedTags.isEmpty {
                Text("none yet")
                    .font(Theme.body(12, italic: true))
                    .foregroundStyle(Theme.textFaint)
            } else {
                FlowLayout(spacing: 5) {
                    ForEach(extractedTags, id: \.self) { tag in
                        TagPill(name: tag, colorHex: "#c9a96e")
                    }
                }
            }
            Spacer()
        }
        .padding(.horizontal, 19)
        .padding(.vertical, 11)
        .overlay(alignment: .top) { Rectangle().fill(Theme.border).frame(height: 1) }
    }

    private var footer: some View {
        HStack(spacing: 14) {
            BrandSegmentedControl(selection: $feed,
                                  options: [("private", "Private"), ("shared", "Shared")])
                .frame(width: 190)
            Spacer()
            PhotosPicker(selection: $photoItems, maxSelectionCount: 4,
                         matching: .images) {
                Image(systemName: "photo")
                    .font(.system(size: 18))
                    .foregroundStyle(photoItems.isEmpty ? Theme.textMuted : Theme.accent)
            }
            if !photoItems.isEmpty {
                Text("\(photoItems.count)")
                    .font(Theme.mono(11, weight: .semibold))
                    .foregroundStyle(Theme.accent)
            }
            Button {
                showFileImporter = true
            } label: {
                Image(systemName: "paperclip")
                    .font(.system(size: 18))
                    .foregroundStyle(fileURLs.isEmpty ? Theme.textMuted : Theme.accent)
            }
            if !fileURLs.isEmpty {
                Text("\(fileURLs.count)")
                    .font(Theme.mono(11, weight: .semibold))
                    .foregroundStyle(Theme.accent)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .background(Theme.surface)
    }

    /// File types the document picker offers, mirroring the web composer's
    /// `accept` list (.md/.txt are covered by `.plainText`). The server's
    /// ALLOWED_EXTENSIONS is the source of truth and rejects anything else.
    private var importTypes: [UTType] {
        let exts = ["md", "txt", "pdf", "doc", "docx", "csv", "xls", "xlsx",
                    "pptx", "m4a", "mp3", "wav", "ogg", "mp4", "mov", "zip"]
        var types = exts.compactMap { UTType(filenameExtension: $0) }
        types.append(.plainText)
        return types
    }

    private var extractedTags: [String] {
        Self.hashtags(in: text)
    }

    static func hashtags(in text: String) -> [String] {
        let matches = text.matches(of: /#([A-Za-z0-9_]+)/)
        var seen = Set<String>()
        return matches.compactMap { match in
            let tag = String(match.1).uppercased()
            return seen.insert(tag).inserted ? tag : nil
        }
    }

    /// Strips #hashtags from the body, matching the design's composer behavior.
    static func stripHashtags(from text: String) -> String {
        text.replacing(/\s?#[A-Za-z0-9_]+/, with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func save() async {
        guard let api = session.api else { return }
        saving = true
        defer { saving = false }
        do {
            let tags = extractedTags
            let body = Self.stripHashtags(from: text)
            var content = body
            var todos: [TodoItem] = []
            if mode == "todo" {
                var lines = body.components(separatedBy: "\n")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                content = lines.isEmpty ? "To-Do" : lines.removeFirst()
                todos = lines.map { line in
                    // "[x] item" round-trips a completed item, like the web UI.
                    if let range = line.range(of: #"^\[( |x|X)\]\s*"#,
                                              options: .regularExpression) {
                        let checked = line[range].lowercased().contains("x")
                        return TodoItem(id: nil,
                                        text: String(line[range.upperBound...]),
                                        checked: checked)
                    }
                    return TodoItem(id: nil, text: line, checked: false)
                }
            }

            let note: Note
            if let editing = editingNote {
                var fields: [String: Any] = [
                    "content": content, "tags": tags, "feed": feed, "type": mode,
                ]
                if mode == "todo" {
                    fields["todos"] = todos.map { ["text": $0.text, "checked": $0.checked] }
                }
                note = try await api.updateNote(id: editing.id, fields: fields)
            } else if mode == "todo" {
                note = try await api.createNote(content: content, tags: tags, feed: feed,
                                                type: "todo", todos: todos)
            } else {
                note = try await api.createNote(content: content, tags: tags, feed: feed)
            }
            try await attachFiles(to: note, api: api)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Uploads any picked photos and document files, then appends all their
    /// markdown links to the note in a single update (so the second batch
    /// doesn't overwrite the first's content).
    private func attachFiles(to note: Note, api: APIClient) async throws {
        var links: [String] = []
        for item in photoItems {
            guard let data = try? await item.loadTransferable(type: Data.self),
                  let image = UIImage(data: data),
                  let jpeg = image.jpegData(compressionQuality: 0.85) else { continue }
            let upload = try await api.uploadAttachment(
                noteID: note.id, data: jpeg, filename: "photo.jpg", mimeType: "image/jpeg")
            links.append(upload.markdown)
        }
        for url in fileURLs {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            guard let data = try? Data(contentsOf: url) else { continue }
            let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType
                ?? "application/octet-stream"
            let upload = try await api.uploadAttachment(
                noteID: note.id, data: data,
                filename: url.lastPathComponent, mimeType: mime)
            links.append(upload.markdown)
        }
        guard !links.isEmpty else { return }
        let content = note.content + "\n\n" + links.joined(separator: "\n")
        _ = try await api.updateNote(id: note.id, fields: ["content": content])
    }
}
