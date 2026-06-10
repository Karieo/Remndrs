import Foundation
import UniformTypeIdentifiers

struct SharedPayload {
    var text: String = ""
    var url: URL?
    var title: String?
    var imageData: [Data] = []
}

/// Extracts text / URLs / images from the host app's NSItemProviders.
struct ShareItemLoader {
    let context: NSExtensionContext?

    func load() async -> SharedPayload {
        var payload = SharedPayload()
        let items = (context?.inputItems as? [NSExtensionItem]) ?? []

        for item in items {
            // Safari puts the page title here.
            if payload.title == nil,
               let attributed = item.attributedContentText?.string,
               !attributed.isEmpty {
                payload.title = attributed
            }
            for provider in item.attachments ?? [] {
                if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    if let url = try? await provider.loadItem(
                        forTypeIdentifier: UTType.url.identifier) as? URL,
                       !url.isFileURL {
                        payload.url = payload.url ?? url
                    }
                } else if provider.hasItemConformingToTypeIdentifier(
                    UTType.plainText.identifier) {
                    if payload.text.isEmpty,
                       let text = try? await provider.loadItem(
                        forTypeIdentifier: UTType.plainText.identifier) as? String {
                        payload.text = text
                    }
                } else if provider.hasItemConformingToTypeIdentifier(
                    UTType.image.identifier) {
                    if let data = await loadImageData(from: provider) {
                        payload.imageData.append(data)
                    }
                }
            }
        }
        // Shared plain text that is just a URL behaves like a URL share.
        if payload.url == nil,
           let candidate = URL(string: payload.text.trimmingCharacters(in: .whitespacesAndNewlines)),
           candidate.scheme?.hasPrefix("http") == true {
            payload.url = candidate
            payload.text = ""
        }
        if payload.title == payload.url?.absoluteString { payload.title = nil }
        return payload
    }

    private func loadImageData(from provider: NSItemProvider) async -> Data? {
        let item = try? await provider.loadItem(forTypeIdentifier: UTType.image.identifier)
        if let url = item as? URL, url.isFileURL {
            return try? Data(contentsOf: url)
        }
        if let data = item as? Data {
            return data
        }
        return nil
    }
}
