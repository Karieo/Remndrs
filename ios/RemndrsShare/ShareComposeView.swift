import SwiftUI

/// Compact compose sheet shown inside the share extension.
struct ShareComposeView: View {
    let loader: ShareItemLoader
    let onDone: () -> Void
    let onCancel: () -> Void

    @State private var text = ""
    @State private var imageData: [Data] = []
    @State private var feed = "private"
    @State private var posting = false
    @State private var errorMessage: String?

    private var api: APIClient? { APIClient() }

    var body: some View {
        VStack(spacing: 0) {
            header
            if api == nil {
                Spacer()
                Text("Open Remndrs and sign in first.")
                    .font(Theme.body(15, italic: true))
                    .foregroundStyle(Theme.textMuted)
                Spacer()
            } else {
                editor
                footer
            }
        }
        .background(Theme.bg)
        .preferredColorScheme(.dark)
        .task {
            let payload = await loader.load()
            text = payload.text
            imageData = payload.imageData
        }
    }

    private var header: some View {
        HStack {
            Button("Cancel", action: onCancel)
                .font(Theme.body(15))
                .foregroundStyle(Theme.textMuted)
            Spacer()
            (Text("Save to Remnd").foregroundColor(Theme.text)
                + Text("r").foregroundColor(Theme.accent)
                + Text("s").foregroundColor(Theme.text))
                .font(Theme.display(16))
            Spacer()
            Button {
                Task { await post() }
            } label: {
                Text(posting ? "Saving…" : "Save")
                    .font(Theme.mono(13, weight: .semibold))
                    .foregroundStyle(Theme.bg)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 14)
                    .background(Theme.accent, in: Capsule())
            }
            .disabled(posting || api == nil
                      || (text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                          && imageData.isEmpty))
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }

    private var editor: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextEditor(text: $text)
                .font(Theme.body(15))
                .foregroundStyle(Theme.text)
                .scrollContentBackground(.hidden)
                .frame(maxHeight: .infinity)
                .padding(.horizontal, 12)
            if !imageData.isEmpty {
                Text("\(imageData.count) image\(imageData.count == 1 ? "" : "s") attached")
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.accent)
                    .padding(.horizontal, 16)
            }
            if let errorMessage {
                Text(errorMessage)
                    .font(Theme.mono(11))
                    .foregroundStyle(Color(hex: 0xF87171))
                    .padding(.horizontal, 16)
            }
        }
    }

    private var footer: some View {
        HStack {
            Picker("Feed", selection: $feed) {
                Text("Private").tag("private")
                Text("Shared").tag("shared")
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Theme.surface)
    }

    private func post() async {
        guard let api else { return }
        posting = true
        defer { posting = false }
        do {
            let tags = extractTags(from: text)
            let body = text.replacing(/\s?#[A-Za-z0-9_]+/, with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let note = try await api.createNote(
                content: body.isEmpty ? "Shared from iOS" : body,
                tags: tags, feed: feed)

            var links: [String] = []
            for data in imageData {
                let upload = try await api.uploadAttachment(
                    noteID: note.id, data: data,
                    filename: "shared.jpg", mimeType: "image/jpeg")
                links.append(upload.markdown)
            }
            if !links.isEmpty {
                let content = note.content + "\n\n" + links.joined(separator: "\n")
                _ = try await api.updateNote(id: note.id, fields: ["content": content])
            }
            onDone()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func extractTags(from text: String) -> [String] {
        var seen = Set<String>()
        return text.matches(of: /#([A-Za-z0-9_]+)/).compactMap { match in
            let tag = String(match.1).uppercased()
            return seen.insert(tag).inserted ? tag : nil
        }
    }
}
