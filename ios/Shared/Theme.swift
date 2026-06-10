import SwiftUI

/// Brand palette + type from the Remndrs design (warm dark, serif, gold accent).
enum Theme {
    // Surfaces
    static let bg = Color(hex: 0x1C1814)
    static let surface = Color(hex: 0x252018)
    static let surface2 = Color(hex: 0x2E2820)
    static let surface3 = Color(hex: 0x3A3028)
    static let pinnedSurface = Color(hex: 0x221E14)
    static let border = Color(hex: 0x3D3428)
    static let border2 = Color(hex: 0x504438)

    // Text
    static let text = Color(hex: 0xE8DCC8)
    static let textMid = Color(hex: 0xB8A890)
    static let textMuted = Color(hex: 0x8A7A65)
    static let textFaint = Color(hex: 0x5A4E40)

    static let accent = Color(hex: 0xC9A96E)

    // Type — bundled OFL fonts; named instances of the variable fonts.
    static func display(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        let name: String
        switch weight {
        case .bold: name = "PlayfairDisplay-Bold"
        case .medium: name = "PlayfairDisplay-Medium"
        default: name = "PlayfairDisplay-SemiBold"
        }
        return .custom(name, size: size)
    }

    static func body(_ size: CGFloat, weight: Font.Weight = .regular,
                     italic: Bool = false) -> Font {
        if italic { return .custom("Lora-Italic", size: size) }
        switch weight {
        case .semibold, .bold: return .custom("Lora-SemiBold", size: size)
        case .medium: return .custom("Lora-Medium", size: size)
        default: return .custom("Lora-Regular", size: size)
        }
    }

    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        switch weight {
        case .semibold, .bold: return .custom("IBMPlexMono-SemiBold", size: size)
        case .medium: return .custom("IBMPlexMono-Medium", size: size)
        default: return .custom("IBMPlexMono", size: size)
        }
    }
}

/// Source channels, exactly as in the design (color + icon + label).
enum Channel: String, CaseIterable {
    case sms, voice, email, calendar, app

    init(source: String) {
        switch source {
        case "sms": self = .sms
        case "voice": self = .voice
        case "email": self = .email
        default: self = .app   // 'web' and 'ios' both read as App
        }
    }

    var label: String {
        switch self {
        case .sms: return "SMS"
        case .voice: return "Voice"
        case .email: return "Email"
        case .calendar: return "Calendar"
        case .app: return "App"
        }
    }

    var color: Color {
        switch self {
        case .sms: return Color(hex: 0x4ADE80)
        case .voice: return Color(hex: 0xA78BFA)
        case .email: return Color(hex: 0xFB923C)
        case .calendar: return Color(hex: 0x7C6FCD)
        case .app: return Color(hex: 0xC9A96E)
        }
    }

    /// SF Symbols standing in for the design's stroke icons.
    var symbol: String {
        switch self {
        case .sms: return "bubble.left"
        case .voice: return "mic"
        case .email: return "envelope"
        case .calendar: return "calendar"
        case .app: return "iphone"
        }
    }

    /// Maps to the API's `source` query param; calendar events come from
    /// a different endpoint, and App covers both web and ios.
    var sourceFilter: String? {
        switch self {
        case .sms: return "sms"
        case .voice: return "voice"
        case .email: return "email"
        case .calendar, .app: return nil
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }

    /// Parses "#4ade80" tag colors from the API; falls back to the accent.
    init(hexString: String) {
        var s = hexString.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        self.init(hex: UInt32(s, radix: 16) ?? 0xC9A96E)
    }
}
