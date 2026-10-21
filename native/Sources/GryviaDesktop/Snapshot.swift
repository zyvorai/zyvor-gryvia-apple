// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import AppKit

/// `GryviaDesktop --snapshot DIR [--server URL] [--token-env VAR]` renders every pane, light and dark, to PNGs in DIR and
/// exits. It is a design-review aid for machines where screen capture is unavailable. The token comes from an
/// environment variable (never the Keychain), and nothing is saved.
enum DesignSnapshot {
    struct Options { let dir: URL; let server: String; let token: String }

    static func options(_ args: [String] = CommandLine.arguments, env: [String: String] = ProcessInfo.processInfo.environment) -> Options? {
        guard let i = args.firstIndex(of: "--snapshot"), args.indices.contains(i + 1) else { return nil }
        func value(_ flag: String) -> String? { args.firstIndex(of: flag).flatMap { args.indices.contains($0 + 1) ? args[$0 + 1] : nil } }
        let tokenVar = value("--token-env") ?? "GRYVIA_ADMIN_TOKEN"
        return Options(dir: URL(fileURLWithPath: args[i + 1]), server: value("--server") ?? "http://127.0.0.1:8443", token: env[tokenVar] ?? "")
    }

    @MainActor static func run(_ o: Options) async {
        try? FileManager.default.createDirectory(at: o.dir, withIntermediateDirectories: true)
        let fleet = Fleet(snapshotServer: o.server, token: o.token)
        await fleet.refresh()
        try? await Task.sleep(for: .seconds(1))
        await fleet.refresh()
        for (scheme, name) in [(NSAppearance.Name.aqua, "light"), (NSAppearance.Name.darkAqua, "dark")] {
            for pane in Pane.allCases {
                let host = NSHostingView(rootView: ContentView(fleet: fleet, start: pane, offersWelcome: false))
                let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
                window.appearance = NSAppearance(named: scheme)
                window.contentView = host
                window.makeKeyAndOrderFront(nil)
                try? await Task.sleep(for: .seconds(1.2))
                guard let view = window.contentView?.superview ?? window.contentView, let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { print("no bitmap for \(pane.rawValue)"); continue }
                view.cacheDisplay(in: view.bounds, to: rep)
                let file = o.dir.appendingPathComponent("native-\(pane.rawValue.lowercased().replacingOccurrences(of: " ", with: "-"))-\(name).png")
                if let png = rep.representation(using: .png, properties: [:]) { try? png.write(to: file); print("wrote", file.path); fflush(stdout) }
                window.orderOut(nil)
            }
        }
        for (scheme, name) in [(NSAppearance.Name.aqua, "light"), (NSAppearance.Name.darkAqua, "dark")] {
            for (label, view) in [("welcome", AnyView(WelcomeView(onDone: {}, onConnect: {}))), ("about", AnyView(AboutView()))] {
                let host = NSHostingView(rootView: view)
                let window = NSWindow(contentRect: NSRect(origin: .zero, size: host.fittingSize), styleMask: [.titled], backing: .buffered, defer: false)
                window.appearance = NSAppearance(named: scheme); window.contentView = host; window.makeKeyAndOrderFront(nil)
                try? await Task.sleep(for: .seconds(0.8))
                if let v = window.contentView?.superview ?? window.contentView, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) {
                    v.cacheDisplay(in: v.bounds, to: rep)
                    let file = o.dir.appendingPathComponent("native-\(label)-\(name).png")
                    if let png = rep.representation(using: .png, properties: [:]) { try? png.write(to: file); print("wrote", file.path); fflush(stdout) }
                }
                window.orderOut(nil)
            }
        }
        NSApplication.shared.terminate(nil)
    }
}
#endif
