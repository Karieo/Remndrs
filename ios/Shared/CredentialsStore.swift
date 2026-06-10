import Foundation
import Security

struct Credentials: Codable {
    var serverURL: URL
    var token: String
    var userID: String
    var userName: String
}

/// Stores credentials in a keychain item shared (via keychain access group)
/// between the app and the share extension.
enum CredentialsStore {
    private static let account = "remndrs"
    private static let service = "com.remndrs.credentials"

    private static var accessGroupQuery: [String: Any] {
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        // The full group is "<TeamID>.com.remndrs.shared"; the system resolves
        // the prefix automatically when only one matches the entitlement.
        #if !targetEnvironment(simulator)
        query[kSecAttrAccessGroup as String] = Bundle.main
            .object(forInfoDictionaryKey: "AppIdentifierPrefix")
            .flatMap { "\($0)\(AppGroup.keychainAccessGroup)" }
            ?? AppGroup.keychainAccessGroup
        #endif
        return query
    }

    static func load() -> Credentials? {
        var query = accessGroupQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(Credentials.self, from: data)
    }

    static func save(_ credentials: Credentials) {
        guard let data = try? JSONEncoder().encode(credentials) else { return }
        var query = accessGroupQuery
        SecItemDelete(query as CFDictionary)
        query[kSecValueData as String] = data
        // AfterFirstUnlock so background refresh can read it.
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(query as CFDictionary, nil)
    }

    static func clear() {
        SecItemDelete(accessGroupQuery as CFDictionary)
    }
}
