import SwiftUI
import PhotosUI

struct ComposerView: View {
    @EnvironmentObject private var session: SessionModel
    @Environment(\.dismiss) private var dismiss

    @State private var mode = "note"
    @State private var text = ""
    @State private var feed = "private"
    @State private var photoItems: [PhotosPickerItem] = []
    @State private var saving = false
    @State private var errorMessage: String?
    @FocusState private var focused: Bool

    /// Prefill support (share extension paths reuse ShareComposeView instead).
    var initialText: String = ""

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
            text = initialText
            focused = true
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
            Text(mode == "todo" ? "New To-Do" : "New Note")
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
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .background(Theme.surface)
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
            let note: Note
            if mode == "todo" {
                var lines = body.components(separatedBy: "\n")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
                let title = lines.isEmpty ? "To-Do" : lines.removeFirst()
                let todos = lines.map { TodoItem(id: nil, text: $0, checked: false) }
                note = try await api.createNote(content: title, tags: tags, feed: feed,
                                                type: "todo", todos: todos)
            } else {
                note = try await api.createNote(content: body, tags: tags, feed: feed)
            }
            try await attachPhotos(to: note, api: api)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func attachPhotos(to note: Note, api: APIClient) async throws {
        guard !photoItems.isEmpty else { return }
        var links: [String] = []
        for item in photoItems {
            guard let data = try? await item.loadTransferable(type: Data.self),
                  let image = UIImage(data: data),
                  let jpeg = image.jpegData(compressionQuality: 0.85) else { continue }
            let upload = try await api.uploadAttachment(
                noteID: note.id, data: jpeg, filename: "photo.jpg", mimeType: "image/jpeg")
            links.append(upload.markdown)
        }
        if !links.isEmpty {
            let content = note.content + "\n\n" + links.joined(separator: "\n")
            _ = try await api.updateNote(id: note.id, fields: ["content": content])
        }
    }
}
