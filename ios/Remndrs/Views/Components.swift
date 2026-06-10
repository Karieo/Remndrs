import SwiftUI

/// Channel chip — icon + uppercase mono label in the channel color (design A1).
struct ChannelChip: View {
    let channel: Channel

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: channel.symbol).font(.system(size: 10, weight: .semibold))
            Text(channel.label.uppercased())
                .font(Theme.mono(9.5, weight: .semibold))
                .kerning(0.5)
        }
        .foregroundStyle(channel.color)
        .padding(.vertical, 3)
        .padding(.horizontal, 8)
        .background(channel.color.opacity(0.14), in: Capsule())
        .overlay(Capsule().strokeBorder(channel.color.opacity(0.35), lineWidth: 1))
    }
}

/// Tag pill — colored tick + uppercase mono name with a tinted border.
struct TagPill: View {
    let name: String
    let colorHex: String

    private var color: Color { Color(hexString: colorHex) }

    var body: some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 1)
                .fill(color)
                .frame(width: 2, height: 11)
            Text(name.uppercased())
                .font(Theme.mono(9.5, weight: .semibold))
                .kerning(0.5)
        }
        .foregroundStyle(color)
        .padding(.vertical, 2)
        .padding(.horizontal, 7)
        .overlay(RoundedRectangle(cornerRadius: 3)
            .strokeBorder(color.opacity(0.4), lineWidth: 1))
    }
}

/// Mono uppercase segmented control with the gold active pill.
struct BrandSegmentedControl<T: Hashable>: View {
    @Binding var selection: T
    let options: [(T, String)]
    var badge: [T: Int] = [:]

    var body: some View {
        HStack(spacing: 3) {
            ForEach(options, id: \.0) { value, label in
                let active = selection == value
                Button {
                    withAnimation(.snappy(duration: 0.18)) { selection = value }
                } label: {
                    HStack(spacing: 6) {
                        Text(label.uppercased())
                            .font(Theme.mono(11, weight: .semibold))
                            .kerning(0.4)
                        if let count = badge[value], count > 0 {
                            Text("\(count)")
                                .font(Theme.mono(9, weight: .semibold))
                                .foregroundStyle(active ? Theme.accent : Theme.bg)
                                .padding(.horizontal, 4)
                                .frame(minWidth: 16, minHeight: 16)
                                .background(active ? Theme.bg : Theme.accent, in: Capsule())
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 7)
                    .foregroundStyle(active ? Theme.bg : Theme.textMuted)
                    .background(active ? Theme.accent : .clear,
                                in: RoundedRectangle(cornerRadius: 6))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(3)
        .background(Theme.surface2, in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(Theme.border, lineWidth: 1))
    }
}

/// Horizontal channel filter scroller ("All" + one chip per channel).
struct ChannelScroller: View {
    @Binding var selection: Channel?

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 7) {
                filterChip(label: "All", color: Theme.accent, symbol: nil,
                           active: selection == nil) { selection = nil }
                ForEach(Channel.allCases, id: \.self) { channel in
                    filterChip(label: channel.label, color: channel.color,
                               symbol: channel.symbol, active: selection == channel) {
                        selection = selection == channel ? nil : channel
                    }
                }
            }
            .padding(.horizontal, 18)
        }
    }

    private func filterChip(label: String, color: Color, symbol: String?,
                            active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let symbol { Image(systemName: symbol).font(.system(size: 11, weight: .semibold)) }
                Text(label.uppercased())
                    .font(Theme.mono(11, weight: .semibold))
                    .kerning(0.4)
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 13)
            .foregroundStyle(active ? color : Theme.textMuted)
            .background(active ? color.opacity(0.14) : Theme.surface, in: Capsule())
            .overlay(Capsule().strokeBorder(
                active ? color.opacity(0.55) : Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

/// Sender avatar — colored circle with mono initials.
struct Avatar: View {
    let name: String
    var size: CGFloat = 34

    private var initials: String {
        let parts = name.split(separator: " ").prefix(2)
        return parts.map { String($0.prefix(1)).uppercased() }.joined()
    }

    private var color: Color {
        let palette: [UInt32] = [0x4ADE80, 0x60A5FA, 0xFB923C, 0xA78BFA, 0xF472B6, 0x2DD4BF]
        let index = abs(name.hashValue) % palette.count
        return Color(hex: palette[index])
    }

    var body: some View {
        Text(initials.isEmpty ? "?" : initials)
            .font(Theme.mono(size * 0.35, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(color, in: Circle())
    }
}

extension Date {
    /// "May 24" for older entries, "11:30 AM" for today — matches the design.
    var cardLabel: String {
        let formatter = DateFormatter()
        if Calendar.current.isDateInToday(self) {
            formatter.dateFormat = "h:mm a"
        } else {
            formatter.dateFormat = "MMM d"
        }
        return formatter.string(from: self)
    }
}
