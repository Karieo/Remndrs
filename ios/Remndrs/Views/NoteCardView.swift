import SwiftUI

/// A feed card: pinned/todo/note/shared treatments per the design.
struct NoteCardView: View {
    let note: Note
    let myUserID: String
    var showSender = false
    var onSend: (() -> Void)?
    var onDelete: (() -> Void)?
    var onToggleTodo: ((TodoItem) -> Void)?

    private var channel: Channel { Channel(source: note.source) }
    private var isOutgoing: Bool { note.userId == myUserID }

    private var accentColor: Color {
        if note.pinned { return Theme.accent }
        if let first = note.tags.first { return Color(hexString: first.color) }
        return Theme.border
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if showSender, let name = note.userName {
                senderHeader(name: name)
                    .padding(.bottom, 11)
            } else {
                header
                    .padding(.bottom, 9)
            }

            if !note.tags.isEmpty {
                tagRow.padding(.bottom, 9)
            }

            if note.type == "todo" {
                todoBody
            } else {
                Text(LocalizedStringKey(note.content))
                    .font(Theme.body(15))
                    .lineSpacing(4)
                    .foregroundStyle(Theme.text)
            }

            if let url = firstURL {
                LinkPreviewCard(url: url)
                    .padding(.top, 11)
            }
        }
        .padding(EdgeInsets(top: 14, leading: 15, bottom: 14, trailing: 15))
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(note.pinned ? Theme.pinnedSurface : Theme.surface,
                    in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.border, lineWidth: 1))
        .overlay(alignment: .leading) {
            accentSpine
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.35), radius: 3, y: 1)
        .contextMenu {
            if let onSend {
                Button { onSend() } label: { Label("Send to…", systemImage: "paperplane") }
            }
            if let onDelete {
                Button(role: .destructive) { onDelete() } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
        }
    }

    private var accentSpine: some View {
        Rectangle()
            .fill(accentColor)
            .frame(width: 3)
            .opacity(showSender && isOutgoing ? 0.55 : 1)  // dashed-feel for outgoing
    }

    private var header: some View {
        HStack(spacing: 8) {
            if note.pinned {
                HStack(spacing: 4) {
                    Image(systemName: "pin").font(.system(size: 9, weight: .semibold))
                    Text("PINNED").font(Theme.mono(9.5, weight: .semibold)).kerning(0.5)
                }
                .foregroundStyle(Theme.accent)
                .padding(.vertical, 2).padding(.horizontal, 7)
                .overlay(RoundedRectangle(cornerRadius: 3)
                    .strokeBorder(Theme.accent, lineWidth: 1))
            }
            ChannelChip(channel: channel)
            Spacer()
            if let date = note.createdDate {
                Text(date.cardLabel)
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textMuted)
            }
        }
    }

    private func senderHeader(name: String) -> some View {
        HStack(spacing: 10) {
            Avatar(name: isOutgoing ? "You" : name)
            VStack(alignment: .leading, spacing: 3) {
                Text(isOutgoing ? "You" : name)
                    .font(Theme.body(14, weight: .semibold))
                    .foregroundStyle(Theme.text)
                HStack(spacing: 6) {
                    HStack(spacing: 3) {
                        Image(systemName: isOutgoing ? "arrow.right" : "arrow.left")
                            .font(.system(size: 8, weight: .bold))
                        Text(isOutgoing ? "you shared" : "shared with you")
                    }
                    .font(Theme.mono(10))
                    .foregroundStyle(isOutgoing ? Color(hex: 0x7C6FCD) : Color(hex: 0x4ADE80))
                    Text("·").foregroundStyle(Theme.textFaint)
                    ChannelChip(channel: channel)
                }
            }
            Spacer()
            if let date = note.createdDate {
                Text(date.cardLabel)
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textMuted)
            }
        }
    }

    private var tagRow: some View {
        FlowLayout(spacing: 5) {
            ForEach(note.tags, id: \.name) { tag in
                TagPill(name: tag.name, colorHex: tag.color)
            }
        }
    }

    private var todoBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !note.content.isEmpty {
                Text(note.content.components(separatedBy: "\n").first ?? note.content)
                    .font(Theme.display(16))
                    .foregroundStyle(Theme.text)
                    .padding(.bottom, 7)
            }
            let done = note.todos.filter(\.checked).count
            HStack(spacing: 9) {
                Text("\(done) / \(note.todos.count)")
                    .font(Theme.mono(11))
                    .foregroundStyle(Theme.textMuted)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Theme.surface3)
                        Capsule().fill(accentColor)
                            .frame(width: note.todos.isEmpty ? 0 :
                                geo.size.width * CGFloat(done) / CGFloat(note.todos.count))
                    }
                }
                .frame(height: 4)
            }
            .padding(.bottom, 11)

            ForEach(note.todos, id: \.self) { todo in
                Button {
                    onToggleTodo?(todo)
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 5)
                                .fill(todo.checked ? accentColor : .clear)
                            RoundedRectangle(cornerRadius: 5)
                                .strokeBorder(todo.checked ? accentColor : Theme.border2,
                                              lineWidth: 1.5)
                            if todo.checked {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(Theme.bg)
                            }
                        }
                        .frame(width: 19, height: 19)
                        Text(todo.text)
                            .font(Theme.body(14.5))
                            .strikethrough(todo.checked)
                            .foregroundStyle(todo.checked ? Theme.textFaint : Theme.text)
                            .multilineTextAlignment(.leading)
                    }
                    .padding(.vertical, 5)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var firstURL: String? {
        let pattern = #"https?://[^\s)>\]]+"#
        guard let range = note.content.range(of: pattern, options: .regularExpression)
        else { return nil }
        return String(note.content[range])
    }
}

/// Calendar event card — fixed purple spine, location row, dimmed when past.
struct EventCardView: View {
    let event: CalendarEvent

    private var isPast: Bool { (RemndrsDate.parse(event.endAt) ?? .distantFuture) < .now }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                ChannelChip(channel: .calendar)
                if event.isOrphaned {
                    Text("⚠︎ ORPHANED")
                        .font(Theme.mono(9.5, weight: .semibold))
                        .foregroundStyle(Color(hex: 0xF97316))
                }
                Spacer()
                if let date = event.startDate {
                    Text(event.isAllDay ? date.cardLabel :
                            date.formatted(date: .omitted, time: .shortened))
                        .font(Theme.mono(11))
                        .foregroundStyle(Theme.textMuted)
                }
            }
            Text(event.title)
                .font(Theme.display(16))
                .foregroundStyle(Theme.text)
            HStack(spacing: 7) {
                Image(systemName: "mappin.and.ellipse").font(.system(size: 10))
                Text(eventMeta)
            }
            .font(Theme.mono(12))
            .foregroundStyle(Theme.textMuted)
        }
        .padding(EdgeInsets(top: 14, leading: 15, bottom: 14, trailing: 15))
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.border, lineWidth: 1))
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(event.isOrphaned ? Color(hex: 0xF97316) : Channel.calendar.color)
                .frame(width: 3)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .opacity(isPast ? 0.65 : 1)
    }

    private var eventMeta: String {
        var parts: [String] = []
        if let location = event.location, !location.isEmpty { parts.append(location) }
        if event.isAllDay {
            parts.append("All day")
        } else if let start = event.startDate, let end = RemndrsDate.parse(event.endAt) {
            let time = "\(start.formatted(date: .omitted, time: .shortened)) – " +
                       "\(end.formatted(date: .omitted, time: .shortened))"
            parts.append(time)
        }
        return parts.joined(separator: " · ")
    }
}

/// Inline OG link preview, fetched from the server's cached /api/preview.
struct LinkPreviewCard: View {
    let url: String
    @EnvironmentObject private var session: SessionModel
    @State private var preview: LinkPreview?

    var body: some View {
        Group {
            if let preview, let title = preview.title {
                HStack(spacing: 11) {
                    Image(systemName: "link")
                        .font(.system(size: 16))
                        .foregroundStyle(Theme.textMuted)
                        .frame(width: 44, height: 44)
                        .background(Theme.surface3, in: RoundedRectangle(cornerRadius: 5))
                    VStack(alignment: .leading, spacing: 3) {
                        if let site = preview.siteName {
                            Text(site.uppercased())
                                .font(Theme.mono(9.5)).kerning(0.5)
                                .foregroundStyle(Theme.textMuted)
                        }
                        Text(title)
                            .font(Theme.body(13, weight: .semibold))
                            .foregroundStyle(Theme.text)
                            .lineLimit(2)
                    }
                    Spacer(minLength: 0)
                }
                .padding(10)
                .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 7))
                .overlay(RoundedRectangle(cornerRadius: 7)
                    .strokeBorder(Theme.border, lineWidth: 1))
            }
        }
        .task(id: url) {
            preview = try? await session.api?.linkPreview(url: url)
        }
    }
}

/// Minimal left-aligned wrapping layout for tag pills.
struct FlowLayout: Layout {
    var spacing: CGFloat = 5

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        layout(proposal: proposal, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        let result = layout(proposal: proposal, subviews: subviews)
        for (subview, position) in zip(subviews, result.positions) {
            subview.place(at: CGPoint(x: bounds.minX + position.x,
                                      y: bounds.minY + position.y),
                          proposal: .unspecified)
        }
    }

    private func layout(proposal: ProposedViewSize,
                        subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > maxWidth {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: maxWidth == .infinity ? x : maxWidth, height: y + rowHeight),
                positions)
    }
}
