import SwiftUI

/// "Send this note" bottom sheet — push a note back out via SMS, email,
/// or into an iCloud calendar (design B4).
struct SendSheetView: View {
    let note: Note
    @EnvironmentObject private var session: SessionModel
    @Environment(\.dismiss) private var dismiss

    enum Destination: String, CaseIterable {
        case sms, email, calendar

        var channel: Channel {
            switch self {
            case .sms: return .sms
            case .email: return .email
            case .calendar: return .calendar
            }
        }
    }

    @State private var destination: Destination = .sms
    @State private var recipient = ""
    @State private var calendars: [CalendarPref] = []
    @State private var calendarName = ""
    @State private var eventDate = Date().addingTimeInterval(3600)
    @State private var sending = false
    @State private var status: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Send this note")
                .font(Theme.display(20))
                .foregroundStyle(Theme.text)
                .padding(.top, 18)
            Text("PUSH IT BACK OUT — ANYWHERE")
                .font(Theme.mono(11)).kerning(0.5)
                .foregroundStyle(Theme.textMuted)
                .padding(.top, 4)

            Text(note.content.components(separatedBy: "\n").first ?? "")
                .font(Theme.body(14, italic: true))
                .foregroundStyle(Theme.textMid)
                .lineLimit(2)
                .padding(.leading, 12)
                .overlay(alignment: .leading) {
                    Rectangle().fill(Theme.border2).frame(width: 2)
                }
                .padding(.top, 16)

            destinationPicker
                .padding(.top, 18)

            inputRow
                .padding(.top, 18)

            Button {
                Task { await send() }
            } label: {
                Text(sending ? "Sending…" : sendLabel)
                    .font(Theme.mono(14, weight: .semibold)).kerning(0.4)
                    .foregroundStyle(Theme.bg)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(Theme.accent, in: RoundedRectangle(cornerRadius: 13))
            }
            .disabled(sending)
            .padding(.top, 18)

            if let status {
                Text(status)
                    .font(Theme.mono(11))
                    .foregroundStyle(Color(hex: 0xF87171))
                    .padding(.top, 8)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 18)
        .background(Theme.surface)
        .task { await loadCalendars() }
    }

    private var sendLabel: String {
        switch destination {
        case .sms: return "Send via SMS →"
        case .email: return "Send via Email →"
        case .calendar: return "Add to Calendar →"
        }
    }

    private var destinationPicker: some View {
        HStack(spacing: 9) {
            ForEach(Destination.allCases, id: \.self) { dest in
                let channel = dest.channel
                let selected = destination == dest
                Button {
                    destination = dest
                } label: {
                    VStack(spacing: 7) {
                        Image(systemName: channel.symbol)
                            .font(.system(size: 17, weight: .medium))
                        Text(channel.label.uppercased())
                            .font(Theme.mono(10)).kerning(0.3)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .foregroundStyle(selected ? channel.color : Theme.textMuted)
                    .background(selected ? channel.color.opacity(0.15) : Theme.surface2,
                                in: RoundedRectangle(cornerRadius: 11))
                    .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(
                        selected ? channel.color : Theme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }

    @ViewBuilder
    private var inputRow: some View {
        switch destination {
        case .sms, .email:
            HStack(spacing: 10) {
                Text("TO")
                    .font(Theme.mono(11)).kerning(0.5)
                    .foregroundStyle(Theme.textFaint)
                TextField("", text: $recipient,
                          prompt: Text(destination == .sms
                                       ? "your number (blank = you)"
                                       : "address (blank = you)")
                            .foregroundStyle(Theme.textFaint))
                    .font(Theme.mono(14))
                    .foregroundStyle(Theme.text)
                    .keyboardType(destination == .sms ? .phonePad : .emailAddress)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
            }
            .padding(.vertical, 13)
            .padding(.horizontal, 15)
            .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Theme.border, lineWidth: 1))
        case .calendar:
            VStack(spacing: 10) {
                if calendars.isEmpty {
                    Text("No calendars enabled — enable one in the Mac app's settings.")
                        .font(Theme.body(13, italic: true))
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
                        .font(Theme.body(14))
                        .tint(Theme.accent)
                }
            }
            .padding(13)
            .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Theme.border, lineWidth: 1))
        }
    }

    private func loadCalendars() async {
        calendars = ((try? await session.api?.calendarPrefs()) ?? [])
            .filter(\.enabled)
        calendarName = calendars.first?.calendarName ?? ""
    }

    private func send() async {
        guard let api = session.api else { return }
        sending = true
        defer { sending = false }
        do {
            switch destination {
            case .sms:
                try await api.sendNote(id: note.id, channel: "sms", to: recipient)
            case .email:
                try await api.sendNote(id: note.id, channel: "email", to: recipient)
            case .calendar:
                guard !calendarName.isEmpty else {
                    status = "Pick a calendar first"
                    return
                }
                try await api.noteToEvent(id: note.id, calendarName: calendarName,
                                          startAt: eventDate,
                                          endAt: eventDate.addingTimeInterval(3600),
                                          allDay: false)
            }
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            dismiss()
        } catch {
            status = error.localizedDescription
        }
    }
}
