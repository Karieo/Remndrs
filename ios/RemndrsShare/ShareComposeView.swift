import SwiftUI

/// "Save to Remndrs" capture sheet — the brand-styled extension UI from the
/// design's inbound-share screens: clipped link preview, note field,
/// channel picker (App / Calendar), live tag chips, gold save button.
struct ShareComposeView: View {
    let loader: ShareItemLoader
    let onDone: () -> Void
    let onCancel: () -> Void

    enum Destination: String { case app, calendar }

    @State private var payload = SharedPayload()
    @State private var note = ""
    @State private var tagInput = ""
    @State private var showTagField = false
    @State private var destination: Destination = .app
    @State private var calendars: [CalendarPref] = []
    @State private var calendarName = ""
    @State private var eventDate = Date().addingTimeInterval(3600)
    @State private var posting = false
    @State private var errorMessage: String?

    private var api: APIClient? { APIClient() }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                sharedFromRow
                if api == nil {
                    Text("Open Remndrs and sign in first.")
                        .font(Theme.body(15, italic: true))
                        .foregroundStyle(Theme.textMuted)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                } else {
                    if payload.url != nil { clipCard }
                    if !payload.imageData.isEmpty {
                        Text("\(payload.imageData.count) image\(payload.imageData.count == 1 ? "" : "s") attached")
                            .font(Theme.mono(11))
                            .foregroundStyle(Theme.accent)
                    }
                    noteField
                    channelPicker
                    tagRow
                    if let errorMessage {
                        Text(errorMessage)
                            .font(Theme.mono(11))
                            .foregroundStyle(Color(hex: 0xF87171))
                    }
                    saveButton
                }
            }
            .padding(18)
        }
        .background(Theme.bg)
        .preferredColorScheme(.dark)
        .task {
            payload = await loader.load()
            note = payload.text
        }
    }

    private var header: some View {
        HStack {
            (Text("Save to Remnd").foregroundColor(Theme.text)
                + Text("r").foregroundColor(Theme.accent)
                + Text("s").foregroundColor(Theme.text))
                .font(Theme.display(18, weight: .bold))
            Spacer()
            Button("Cancel", action: onCancel)
                .font(Theme.body(15))
                .foregroundStyle(Theme.textMuted)
        }
        .padding(.top, 6)
    }

    private var sharedFromRow: some View {
        HStack(spacing: 5) {
            Image(systemName: "square.and.arrow.up").font(.system(size: 10))
            Text(sourceLabel.uppercased()).kerning(0.5)
        }
        .font(Theme.mono(10))
        .foregroundStyle(Theme.textMuted)
    }

    private var sourceLabel: String {
        if let host = payload.url?.host() { return "Shared from \(host)" }
        if !payload.imageData.isEmpty { return "Shared images" }
        return "Shared content"
    }

    private var clipCard: some View {
        HStack(spacing: 12) {
            Text(String(siteName.prefix(1)).uppercased())
                .font(Theme.display(20, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: 46, height: 46)
                .background(
                    LinearGradient(colors: [Color(hex: 0xFF7A45), Color(hex: 0xFF5A36)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 3) {
                Text(siteName.uppercased())
                    .font(Theme.mono(9.5)).kerning(0.5)
                    .foregroundStyle(Theme.textMuted)
                if let title = payload.title {
                    Text(title)
                        .font(Theme.body(13.5, weight: .semibold))
                        .foregroundStyle(Theme.text)
                        .lineLimit(2)
                }
                Text(payload.url?.absoluteString ?? "")
                    .font(Theme.mono(10))
                    .foregroundStyle(Theme.textFaint)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 11))
        .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Theme.border, lineWidth: 1))
    }

    private var siteName: String {
        let host = payload.url?.host() ?? "link"
        let parts = host.split(separator: ".")
        let root = parts.count >= 2 ? String(parts[parts.count - 2]) : host
        return root
    }

    private var noteField: some View {
        ZStack(alignment: .topLeading) {
            TextEditor(text: $note)
                .font(Theme.body(14.5))
                .foregroundStyle(Theme.text)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 74, maxHeight: 140)
                .padding(.horizontal, 9)
                .padding(.vertical, 5)
            if note.isEmpty {
                Text("Add a note…")
                    .font(Theme.body(14.5, italic: true))
                    .foregroundStyle(Theme.textFaint)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 13)
                    .allowsHitTesting(false)
            }
        }
        .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 11))
        .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Theme.border, lineWidth: 1))
    }

    private var channelPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("SAVE TO CHANNEL")
                .font(Theme.mono(9.5)).kerning(0.6)
                .foregroundStyle(Theme.textFaint)
            HStack(spacing: 7) {
                channelChip("App", channel: .app, selected: destination == .app) {
                    destination = .app
                }
                channelChip("Calendar", channel: .calendar,
                            selected: destination == .calendar) {
                    destination = .calendar
                    Task { await loadCalendars() }
                }
            }
            if destination == .calendar {
                VStack(spacing: 8) {
                    if calendars.isEmpty {
                        Text("No calendars enabled — enable one in the Mac app first.")
                            .font(Theme.body(12, italic: true))
                            .foregroundStyle(Theme.textMuted)
                    } else {
                        Picker("Calendar", selection: $calendarName) {
                            ForEach(calendars, id: \.calendarName) { pref in
                                Text(pref.calendarName).tag(pref.calendarName)
                            }
                        }
                        .pickerStyle(.menu)
                        .tint(Theme.accent)
                        DatePicker("Starts", selection: $eventDate)
                            .font(Theme.body(13))
                            .tint(Theme.accent)
                    }
                }
                .padding(11)
                .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 11))
                .overlay(RoundedRectangle(cornerRadius: 11)
                    .strokeBorder(Theme.border, lineWidth: 1))
            }
        }
    }

    private func channelChip(_ label: String, channel: Channel, selected: Bool,
                             action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: channel.symbol).font(.system(size: 11, weight: .semibold))
                Text(label.uppercased())
                    .font(Theme.mono(10.5, weight: .semibold)).kerning(0.4)
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 12)
            .foregroundStyle(selected ? channel.color : Theme.textMuted)
            .background(selected ? channel.color.opacity(0.16) : Theme.surface2,
                        in: Capsule())
            .overlay(Capsule().strokeBorder(
                selected ? channel.color : Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var extractedTags: [String] {
        var seen = Set<String>()
        var tags: [String] = []
        for match in note.matches(of: /#([A-Za-z0-9_]+)/) {
            let tag = String(match.1).uppercased()
            if seen.insert(tag).inserted { tags.append(tag) }
        }
        for raw in tagInput.split(whereSeparator: { ", ".contains($0) }) {
            let tag = raw.trimmingCharacters(in: .whitespaces)
                .trimmingCharacters(in: CharacterSet(charactersIn: "#")).uppercased()
            if !tag.isEmpty, seen.insert(tag).inserted { tags.append(tag) }
        }
        return tags
    }

    private var tagRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("TAGS")
                .font(Theme.mono(9.5)).kerning(0.6)
                .foregroundStyle(Theme.textFaint)
            FlowRow(spacing: 7) {
                ForEach(extractedTags, id: \.self) { tag in
                    TagPill(name: tag, colorHex: "#c9a96e")
                }
                Button {
                    showTagField.toggle()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "plus").font(.system(size: 9, weight: .semibold))
                        Text("TAG").font(Theme.mono(9.5, weight: .semibold)).kerning(0.5)
                    }
                    .foregroundStyle(Theme.textMuted)
                    .padding(.vertical, 3)
                    .padding(.horizontal, 8)
                    .overlay(RoundedRectangle(cornerRadius: 3)
                        .strokeBorder(Theme.border2, style: StrokeStyle(lineWidth: 1, dash: [3])))
                }
                .buttonStyle(.plain)
            }
            if showTagField {
                TextField("", text: $tagInput,
                          prompt: Text("tags, comma separated")
                            .font(Theme.body(13, italic: true))
                            .foregroundStyle(Theme.textFaint))
                    .font(Theme.mono(12))
                    .foregroundStyle(Theme.text)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 11)
                    .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(Theme.border, lineWidth: 1))
            }
        }
    }

    private var saveButton: some View {
        Button {
            Task { await post() }
        } label: {
            Text(posting ? "Saving…" : "Save note →")
                .font(Theme.mono(14, weight: .semibold)).kerning(0.4)
                .foregroundStyle(Theme.bg)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .background(Theme.accent, in: RoundedRectangle(cornerRadius: 13))
        }
        .buttonStyle(.plain)
        .disabled(posting || !hasContent)
    }

    private var hasContent: Bool {
        !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || payload.url != nil || payload.title != nil || !payload.imageData.isEmpty
    }

    private func post() async {
        guard let api else { return }
        posting = true
        defer { posting = false }
        do {
            let tags = extractedTags
            var body = note.replacing(/\s?#[A-Za-z0-9_]+/, with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if body.isEmpty, let title = payload.title { body = title }
            if let url = payload.url {
                body = body.isEmpty ? url.absoluteString : body + "\n\n" + url.absoluteString
            }
            if body.isEmpty { body = "Shared from iOS" }
            let feed = tags.contains("SHARED") ? "shared" : "private"
            let created = try await api.createNote(content: body, tags: tags, feed: feed)

            var links: [String] = []
            for data in payload.imageData {
                let upload = try await api.uploadAttachment(
                    noteID: created.id, data: data,
                    filename: "shared.jpg", mimeType: "image/jpeg")
                links.append(upload.markdown)
            }
            if !links.isEmpty {
                let content = created.content + "\n\n" + links.joined(separator: "\n")
                _ = try await api.updateNote(id: created.id, fields: ["content": content])
            }
            if destination == .calendar, !calendarName.isEmpty {
                try await api.noteToEvent(id: created.id, calendarName: calendarName,
                                          startAt: eventDate,
                                          endAt: eventDate.addingTimeInterval(3600),
                                          allDay: false)
            }
            onDone()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadCalendars() async {
        guard calendars.isEmpty, let api else { return }
        calendars = ((try? await api.calendarPrefs()) ?? []).filter(\.enabled)
        calendarName = calendars.first?.calendarName ?? ""
    }
}

/// Compact wrapping HStack for the tag chips (extension-local; the app
/// target has its own FlowLayout).
struct FlowRow: Layout {
    var spacing: CGFloat = 7

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal: proposal, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        let result = arrange(proposal: proposal, subviews: subviews)
        for (subview, point) in zip(subviews, result.points) {
            subview.place(at: CGPoint(x: bounds.minX + point.x, y: bounds.minY + point.y),
                          proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize,
                         subviews: Subviews) -> (size: CGSize, points: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var points: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > maxWidth {
                x = 0; y += rowHeight + spacing; rowHeight = 0
            }
            points.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: maxWidth == .infinity ? x : maxWidth, height: y + rowHeight),
                points)
    }
}
