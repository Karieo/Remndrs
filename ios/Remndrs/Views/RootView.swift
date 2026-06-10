import SwiftUI

enum AppTab: String, CaseIterable {
    case notes, capture, shared

    var label: String {
        switch self {
        case .notes: return "Notes"
        case .capture: return "Capture"
        case .shared: return "Shared"
        }
    }

    var symbol: String {
        switch self {
        case .notes: return "house"
        case .capture: return "tray.and.arrow.down"
        case .shared: return "person.2"
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var session: SessionModel
    @State private var tab: AppTab = .notes
    @State private var composing = false

    var body: some View {
        if session.credentials == nil {
            LoginView()
        } else {
            NavigationStack {
                ZStack(alignment: .bottom) {
                    Group {
                        switch tab {
                        case .notes: FeedView()
                        case .capture: CaptureView()
                        case .shared: FeedView(lockedFeed: "shared")
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                    glassTabBar
                }
                .background(Theme.bg)
                .overlay(alignment: .bottomTrailing) {
                    fab
                }
                .toolbar(.hidden, for: .navigationBar)
            }
            .sheet(isPresented: $composing) {
                ComposerView()
            }
        }
    }

    private var glassTabBar: some View {
        HStack {
            ForEach(AppTab.allCases, id: \.self) { item in
                Button {
                    tab = item
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: item.symbol)
                            .font(.system(size: 19, weight: .regular))
                        Text(item.label.uppercased())
                            .font(Theme.mono(8.5))
                            .kerning(0.3)
                    }
                    .frame(maxWidth: .infinity)
                    .foregroundStyle(tab == item ? Theme.accent : Theme.textFaint)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .frame(height: 62)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 26))
        .background(Theme.surface2.opacity(0.72), in: RoundedRectangle(cornerRadius: 26))
        .overlay(RoundedRectangle(cornerRadius: 26).strokeBorder(Theme.border2, lineWidth: 1))
        .shadow(color: .black.opacity(0.4), radius: 15, y: 8)
        .padding(.horizontal, 14)
        .padding(.bottom, 8)
    }

    private var fab: some View {
        Button {
            composing = true
        } label: {
            Image(systemName: "plus")
                .font(.system(size: 26, weight: .light))
                .foregroundStyle(Theme.bg)
                .frame(width: 58, height: 58)
                .background(Theme.accent, in: Circle())
                .shadow(color: Theme.accent.opacity(0.4), radius: 10, y: 6)
        }
        .padding(.trailing, 20)
        .padding(.bottom, 92)
    }
}
