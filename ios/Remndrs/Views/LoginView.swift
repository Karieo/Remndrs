import SwiftUI
import UIKit

struct LoginView: View {
    @EnvironmentObject private var session: SessionModel
    @State private var server = "https://"
    @State private var login = ""
    @State private var password = ""
    @State private var working = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 16) {
            Spacer()
            Wordmark()
            Text("YOUR ALWAYS-ON INBOX")
                .font(Theme.mono(10)).kerning(1)
                .foregroundStyle(Theme.textMuted)
                .padding(.bottom, 16)

            field("Server URL", text: $server, keyboard: .URL)
            field("Name or email", text: $login)
            secureField("Password", text: $password)

            if let errorMessage {
                Text(errorMessage)
                    .font(Theme.mono(11))
                    .foregroundStyle(Color(hex: 0xF87171))
            }

            Button {
                Task { await signIn() }
            } label: {
                Text(working ? "Signing in…" : "Sign in")
                    .font(Theme.mono(14, weight: .semibold)).kerning(0.4)
                    .foregroundStyle(Theme.bg)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(Theme.accent, in: RoundedRectangle(cornerRadius: 13))
            }
            .disabled(working || login.isEmpty || password.isEmpty)
            .padding(.top, 8)

            Spacer()
            Spacer()
        }
        .padding(.horizontal, 28)
        .background(Theme.bg)
    }

    private func field(_ placeholder: String, text: Binding<String>,
                       keyboard: UIKeyboardType = .default) -> some View {
        TextField("", text: text,
                  prompt: Text(placeholder).foregroundStyle(Theme.textFaint))
            .font(Theme.body(15))
            .foregroundStyle(Theme.text)
            .keyboardType(keyboard)
            .autocorrectionDisabled()
            .textInputAutocapitalization(.never)
            .padding(.vertical, 12)
            .padding(.horizontal, 14)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11)
                .strokeBorder(Theme.border, lineWidth: 1))
    }

    private func secureField(_ placeholder: String, text: Binding<String>) -> some View {
        SecureField("", text: text,
                    prompt: Text(placeholder).foregroundStyle(Theme.textFaint))
            .font(Theme.body(15))
            .foregroundStyle(Theme.text)
            .padding(.vertical, 12)
            .padding(.horizontal, 14)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11)
                .strokeBorder(Theme.border, lineWidth: 1))
    }

    private func signIn() async {
        guard let url = URL(string: server.trimmingCharacters(in: .whitespaces)),
              url.scheme?.hasPrefix("http") == true else {
            errorMessage = "Enter the full server URL (https://…)"
            return
        }
        working = true
        defer { working = false }
        do {
            let response = try await APIClient.obtainToken(
                server: url, login: login, password: password,
                deviceName: UIDevice.current.name)
            session.signIn(Credentials(serverURL: url, token: response.token,
                                       userID: response.user.id,
                                       userName: response.user.name))
            await ReminderSyncer.sync()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
