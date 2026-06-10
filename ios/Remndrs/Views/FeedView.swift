import SwiftUI

@MainActor
final class FeedModel: ObservableObject {
    @Published var notes: [Note] = []
    @Published var events: [CalendarEvent] = []
    @Published var feed: String = "private"
    @Published var channel: Channel?
    @Published var search = ""
    @Published var errorMessage: String?

    private var searchTask: Task<Void, Never>?

    func load(api: APIClient?) async {
        guard let api else { return }
        do {
            async let notesResult = api.notes(
                feed: feed,
                search: search.isEmpty ? nil : search,
                source: channel?.sourceFilter)
            async let eventsResult = api.calendarEvents()
            notes = try await notesResult
            events = (try? await eventsResult) ?? []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func debouncedReload(api: APIClient?) {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(250))
            guard !Task.isCancelled else { return }
            await load(api: api)
        }
    }

    /// Feed rows: pinned notes first, then notes + events interleaved by date.
    var rows: [FeedRow] {
        let visibleEvents = (channel == nil || channel == .calendar) && search.isEmpty
            ? events.filter { $0.feed == feed && !$0.isOrphaned }
            : []
        let noteRows = channel == .calendar ? [] : notes
        var items: [FeedRow] = noteRows.map { .note($0) }
        items += visibleEvents.map { .event($0) }
        return items.sorted { a, b in
            if a.pinned != b.pinned { return a.pinned }
            return a.sortDate > b.sortDate
        }
    }
}

enum FeedRow: Identifiable {
    case note(Note)
    case event(CalendarEvent)

    var id: String {
        switch self {
        case .note(let n): return "n-\(n.id)"
        case .event(let e): return "e-\(e.id)"
        }
    }

    var pinned: Bool {
        if case .note(let n) = self { return n.pinned }
        return false
    }

    var sortDate: Date {
        switch self {
        case .note(let n): return n.createdDate ?? .distantPast
        case .event(let e): return e.startDate ?? .distantPast
        }
    }
}

struct FeedView: View {
    @EnvironmentObject private var session: SessionModel
    @StateObject private var model = FeedModel()
    /// When non-nil the feed is locked (Shared tab); otherwise Mine/Shared toggles.
    var lockedFeed: String?
    @State private var sendTarget: Note?
    @State private var sharedCount = 0

    private var myUserID: String { session.credentials?.userID ?? "" }

    var body: some View {
        VStack(spacing: 0) {
            header
            ChannelScroller(selection: $model.channel)
                .padding(.top, 13)
                .padding(.bottom, 4)
            list
        }
        .background(Theme.bg)
        .task {
            model.feed = lockedFeed ?? model.feed
            await model.load(api: session.api)
            await refreshSharedCount()
        }
        .onChange(of: model.feed) { Task { await model.load(api: session.api) } }
        .onChange(of: model.channel) { Task { await model.load(api: session.api) } }
        .onChange(of: model.search) { model.debouncedReload(api: session.api) }
        .sheet(item: $sendTarget) { note in
            SendSheetView(note: note)
                .presentationDetents([.height(420)])
                .presentationDragIndicator(.visible)
                .presentationBackground(Theme.surface)
        }
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack {
                Wordmark()
                Spacer()
                NavigationLink {
                    SettingsView()
                } label: {
                    Avatar(name: session.credentials?.userName ?? "?", size: 32)
                }
            }
            if lockedFeed == nil {
                BrandSegmentedControl(
                    selection: $model.feed,
                    options: [("private", "Mine"), ("shared", "Shared")],
                    badge: ["shared": sharedCount])
            }
            searchBar
        }
        .padding(.horizontal, 18)
        .padding(.top, 8)
    }

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 13))
                .foregroundStyle(Theme.textMuted)
            TextField("", text: $model.search,
                      prompt: Text(model.feed == "shared"
                                   ? "Search shared notes…" : "Search by text or date…")
                        .font(Theme.body(14, italic: true))
                        .foregroundStyle(Theme.textMuted))
                .font(Theme.body(14))
                .foregroundStyle(Theme.text)
                .autocorrectionDisabled()
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 13)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 11))
        .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Theme.border, lineWidth: 1))
    }

    private var list: some View {
        ScrollView {
            LazyVStack(spacing: 13) {
                if let message = model.errorMessage {
                    Text(message)
                        .font(Theme.mono(11))
                        .foregroundStyle(Color(hex: 0xF87171))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                ForEach(model.rows) { row in
                    switch row {
                    case .note(let note):
                        NoteCardView(
                            note: note,
                            myUserID: myUserID,
                            showSender: model.feed == "shared",
                            onSend: { sendTarget = note },
                            onDelete: { Task { await delete(note) } },
                            onToggleTodo: { todo in Task { await toggle(todo, in: note) } })
                    case .event(let event):
                        EventCardView(event: event)
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 10)
            .padding(.bottom, 120)
        }
        .refreshable { await model.load(api: session.api) }
        .scrollDismissesKeyboard(.immediately)
    }

    private func delete(_ note: Note) async {
        try? await session.api?.deleteNote(id: note.id)
        await model.load(api: session.api)
    }

    private func toggle(_ todo: TodoItem, in note: Note) async {
        let updated = note.todos.map { item in
            ["text": item.text,
             "checked": item == todo ? !item.checked : item.checked] as [String: Any]
        }
        _ = try? await session.api?.updateNote(id: note.id, fields: ["todos": updated])
        await model.load(api: session.api)
    }

    private func refreshSharedCount() async {
        sharedCount = (try? await session.api?.notes(feed: "shared").count) ?? 0
    }
}

struct Wordmark: View {
    var body: some View {
        // Remnd<r>s — gold accent on the r, as in the design.
        (Text("Remnd").foregroundColor(Theme.text)
            + Text("r").foregroundColor(Theme.accent)
            + Text("s").foregroundColor(Theme.text))
            .font(Theme.display(26, weight: .bold))
            .kerning(-0.5)
    }
}
