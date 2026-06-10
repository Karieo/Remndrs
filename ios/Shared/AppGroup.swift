import Foundation

/// Shared identifiers. If you change the bundle prefix in project.yml,
/// change these to match and regenerate the project.
enum AppGroup {
    static let identifier = "group.com.remndrs.app"
    static let keychainAccessGroup = "com.remndrs.shared"
    static let backgroundRefreshTaskID = "com.remndrs.refresh"

    static var sharedDefaults: UserDefaults {
        UserDefaults(suiteName: identifier) ?? .standard
    }
}
