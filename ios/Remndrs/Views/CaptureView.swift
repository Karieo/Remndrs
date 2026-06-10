import SwiftUI
import AVFoundation

/// Capture tab: voice memo → Whisper transcription → prefilled composer.
/// Also surfaces the other inbound channels so the omnichannel story is visible.
struct CaptureView: View {
    @EnvironmentObject private var session: SessionModel
    @StateObject private var recorder = VoiceRecorder()
    @State private var transcribing = false
    @State private var draft: String?
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Wordmark()
                Spacer()
            }
            .padding(.horizontal, 18)
            .padding(.top, 8)

            Spacer()

            micButton

            Text(recorder.isRecording ? "Recording — tap to finish"
                 : transcribing ? "Transcribing…"
                 : "Tap to record a voice note")
                .font(Theme.body(15, italic: true))
                .foregroundStyle(Theme.textMuted)
                .padding(.top, 24)

            if let errorMessage {
                Text(errorMessage)
                    .font(Theme.mono(11))
                    .foregroundStyle(Color(hex: 0xF87171))
                    .padding(.top, 10)
            }

            Spacer()

            channelHints
                .padding(.bottom, 120)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bg)
        .sheet(item: .init(
            get: { draft.map(DraftText.init) },
            set: { draft = $0?.text })) { item in
            ComposerView(initialText: item.text)
        }
    }

    private var micButton: some View {
        Button {
            Task { await toggleRecording() }
        } label: {
            ZStack {
                Circle()
                    .fill(recorder.isRecording
                          ? Channel.voice.color.opacity(0.2) : Theme.surface2)
                    .frame(width: 132, height: 132)
                Circle()
                    .strokeBorder(recorder.isRecording
                                  ? Channel.voice.color : Theme.border2, lineWidth: 1.5)
                    .frame(width: 132, height: 132)
                if transcribing {
                    ProgressView().tint(Theme.accent)
                } else {
                    Image(systemName: recorder.isRecording ? "stop.fill" : "mic")
                        .font(.system(size: 40, weight: .light))
                        .foregroundStyle(recorder.isRecording
                                         ? Channel.voice.color : Theme.accent)
                }
            }
        }
        .buttonStyle(.plain)
        .disabled(transcribing)
    }

    private var channelHints: some View {
        VStack(spacing: 9) {
            Text("OTHER WAYS IN")
                .font(Theme.mono(9.5)).kerning(0.5)
                .foregroundStyle(Theme.textFaint)
            HStack(spacing: 7) {
                ChannelChip(channel: .sms)
                ChannelChip(channel: .email)
                ChannelChip(channel: .calendar)
            }
            Text("Text or email your Remndrs inbox — it all lands in the feed.")
                .font(Theme.body(12, italic: true))
                .foregroundStyle(Theme.textFaint)
        }
    }

    private func toggleRecording() async {
        errorMessage = nil
        if recorder.isRecording {
            guard let fileURL = recorder.stop() else { return }
            transcribing = true
            defer { transcribing = false }
            do {
                guard let api = session.api else { return }
                let result = try await api.transcribe(audioURL: fileURL)
                let tags = result.tags
                    .filter { $0 != "VOICE" }
                    .map { "#\($0.lowercased())" }
                    .joined(separator: " ")
                draft = result.transcript + (tags.isEmpty ? "" : "\n\n\(tags)")
            } catch {
                errorMessage = error.localizedDescription
            }
            try? FileManager.default.removeItem(at: fileURL)
        } else {
            await recorder.start()
            if recorder.permissionDenied {
                errorMessage = "Microphone access denied — enable it in Settings."
            }
        }
    }
}

private struct DraftText: Identifiable {
    let text: String
    var id: String { text }
}

@MainActor
final class VoiceRecorder: ObservableObject {
    @Published var isRecording = false
    @Published var permissionDenied = false

    private var recorder: AVAudioRecorder?

    func start() async {
        let granted = await AVAudioApplication.requestRecordPermission()
        guard granted else {
            permissionDenied = true
            return
        }
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .default)
        try? session.setActive(true)

        let url = FileManager.default.temporaryDirectory
            .appending(path: "memo-\(UUID().uuidString).m4a")
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVEncoderBitRateKey: 64_000,
        ]
        recorder = try? AVAudioRecorder(url: url, settings: settings)
        recorder?.record()
        isRecording = recorder?.isRecording ?? false
    }

    func stop() -> URL? {
        guard let recorder else { return nil }
        recorder.stop()
        isRecording = false
        let url = recorder.url
        self.recorder = nil
        try? AVAudioSession.sharedInstance().setActive(false)
        return url
    }
}
