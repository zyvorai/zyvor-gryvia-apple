// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import AppKit
import GryviaCore

enum Product {
    static let tagline = "A control plane for Apple Silicon fleets"
    static let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development build"
    static let site = URL(string: "https://zyvorai.github.io/zyvor-gryvia-apple/")!
    static let demo = URL(string: "https://zyvorai.github.io/zyvor-gryvia-apple/demo/")!
    static let source = URL(string: "https://github.com/zyvorai/zyvor-gryvia-apple")!
    static let security = URL(string: "https://github.com/zyvorai/zyvor-gryvia-apple/blob/main/SECURITY.md")!
}

/// The app icon from the bundle; a vector mark when it is missing (e.g. `swift run`), so the brand never degrades to a folder.
struct BrandMark: View {
    var size: CGFloat = 32
    var body: some View {
        if Bundle.main.url(forResource: "Gryvia", withExtension: "icns") != nil {
            Image(nsImage: ContentView.brandIcon).resizable().frame(width: size, height: size)
        } else {
            let accent = Color(hex: Brand.accentHex)
            ZStack {
                RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
                    .fill(LinearGradient(colors: [accent, accent.opacity(0.65)], startPoint: .topLeading, endPoint: .bottomTrailing))
                Text("G").font(.system(size: size * 0.6, weight: .heavy, design: .rounded)).foregroundStyle(.white)
            }.frame(width: size, height: size).accessibilityHidden(true)
        }
    }
}

/// Queue → admission → Macs, the story the product tells. Time-driven; a still frame under Reduce Motion.
struct FleetIllustration: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(paused: reduceMotion)) { ctx in
            Canvas { g, size in Self.draw(&g, size, reduceMotion ? 1.3 : ctx.date.timeIntervalSinceReferenceDate) }
        }
        .frame(height: 170)
        .accessibilityElement().accessibilityLabel("Jobs wait in a queue, are admitted against each Mac's memory budget, then run on a Mac.")
    }

    static func draw(_ g: inout GraphicsContext, _ size: CGSize, _ t: Double) {
        let accent = Color(hex: Brand.accentHex)
        let ok = Color(hex: Brand.status["succeeded"] ?? 0x30D158)
        let wait = Color(hex: Brand.status["queued"] ?? 0xFF9F0A)
        let w = size.width, h = size.height
        let qx = w * 0.10, gx = w * 0.46, mx = w * 0.80
        let macY = [h * 0.20, h * 0.50, h * 0.80]
        // links
        for y in macY {
            var p = Path(); p.move(to: CGPoint(x: gx, y: h / 2)); p.addCurve(to: CGPoint(x: mx - 34, y: y), control1: CGPoint(x: gx + 50, y: h / 2), control2: CGPoint(x: mx - 90, y: y))
            g.stroke(p, with: .color(accent.opacity(0.25)), style: StrokeStyle(lineWidth: 1.5, dash: [3, 5]))
        }
        var q = Path(); q.move(to: CGPoint(x: qx, y: h / 2)); q.addLine(to: CGPoint(x: gx - 30, y: h / 2))
        g.stroke(q, with: .color(accent.opacity(0.25)), style: StrokeStyle(lineWidth: 1.5, dash: [3, 5]))
        // queue stack
        for i in 0..<3 {
            let r = CGRect(x: qx - 24, y: h / 2 - 30 + CGFloat(i) * 22, width: 48, height: 16)
            g.fill(Path(roundedRect: r, cornerRadius: 8), with: .color(wait.opacity(0.85 - Double(i) * 0.2)))
        }
        // admission gate
        let gate = CGRect(x: gx - 30, y: h / 2 - 34, width: 60, height: 68)
        g.stroke(Path(roundedRect: gate, cornerRadius: 14), with: .color(accent.opacity(0.7)), style: StrokeStyle(lineWidth: 1.5, dash: [5, 4]))
        // Macs: a lit core grid, brightness drifting over time
        for (n, y) in macY.enumerated() {
            let r = CGRect(x: mx - 34, y: y - 18, width: 68, height: 36)
            g.fill(Path(roundedRect: r, cornerRadius: 9), with: .color(accent.opacity(0.10)))
            g.stroke(Path(roundedRect: r, cornerRadius: 9), with: .color(accent.opacity(0.45)), lineWidth: 1)
            for c in 0..<12 {
                let cell = CGRect(x: r.minX + 8 + CGFloat(c % 6) * 9.5, y: r.minY + 8 + CGFloat(c / 6) * 11, width: 7, height: 8)
                let lit = 0.5 + 0.5 * sin(t * 1.4 + Double(c) * 0.9 + Double(n) * 2)
                g.fill(Path(roundedRect: cell, cornerRadius: 2), with: .color(ok.opacity(0.18 + 0.7 * lit)))
            }
        }
        // jobs in flight
        for k in 0..<6 {
            let phase = (t * 0.35 + Double(k) / 6).truncatingRemainder(dividingBy: 1)
            let target = macY[k % 3]
            let p: CGPoint
            if phase < 0.45 { let f = phase / 0.45; p = CGPoint(x: qx + (gx - qx) * f, y: h / 2) }
            else { let f = (phase - 0.45) / 0.55; let e = f * f * (3 - 2 * f); p = CGPoint(x: gx + (mx - 34 - gx) * f, y: h / 2 + (target - h / 2) * e) }
            let dot = CGRect(x: p.x - 4.5, y: p.y - 4.5, width: 9, height: 9)
            g.fill(Path(ellipseIn: dot.insetBy(dx: -4, dy: -4)), with: .color(accent.opacity(0.18)))
            g.fill(Path(ellipseIn: dot), with: .color(phase < 0.45 ? wait : accent))
        }
        g.draw(Text("queue").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: qx, y: h - 6))
        g.draw(Text("admission").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: gx, y: h - 6))
        g.draw(Text("your Macs").font(.caption2).foregroundStyle(.secondary), at: CGPoint(x: mx, y: h - 6))
    }
}

struct AboutView: View {
    var body: some View {
        VStack(spacing: 14) {
            BrandMark(size: 84)
            VStack(spacing: 2) {
                Text("Gryvia").font(.system(.largeTitle, design: .rounded, weight: .bold))
                Text("by Zyvor AI Labs").foregroundStyle(.secondary)
            }
            Text(Product.tagline).font(.headline)
            Text("Your Macs, scheduled. Gryvia places inference, fine-tuning and benchmark jobs on the Mac that has the memory for them, with quotas, owner-aware policy and signed provenance.")
                .font(.callout).multilineTextAlignment(.center).frame(width: 360)
            FleetIllustration().frame(width: 360)
            Text(Product.version.first?.isNumber == true ? "Version \(Product.version)" : Product.version.capitalized).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            Text("Numbers shown are as measured: GPU use is device-wide, reservations are bookkeeping, and energy is an estimate.")
                .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(width: 360)
            Text("Source-available under BUSL-1.1: free to read, build and test, paid to run for real work. Each version becomes Apache-2.0 four years after its first public release.")
                .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(width: 360)
            HStack(spacing: 16) {
                Link("Website", destination: Product.site); Link("Live demo", destination: Product.demo)
                Link("Source", destination: Product.source); Link("Security", destination: Product.security)
            }.font(.callout)
            Text("© 2026 Zyvor AI Labs Private Limited").font(.caption2).foregroundStyle(.tertiary)
        }.padding(28).frame(width: 440).background { AmbientBackground() }
    }
}

struct WelcomeView: View {
    var onDone: () -> Void
    var onConnect: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                BrandMark(size: 44)
                Text("Welcome to Gryvia").font(.system(.title, design: .rounded, weight: .bold))
            }
            Text("Gryvia decides which of your Macs runs each AI job, so nothing overloads a machine's unified memory.").font(.title3)
            FleetIllustration().padding(.vertical, 4)
            VStack(alignment: .leading, spacing: 10) {
                point("tray.full", "Jobs queue, then are admitted", "Each Mac has a memory budget. A job starts only where it fits, by priority and fairness.")
                point("waveform.path.ecg", "You see every Mac live", "GPU cores light up by measured utilisation, with thermal state, drain and owner policy.")
                point("checkmark.shield", "Honest numbers", "Reservations are bookkeeping, GPU use is device-wide, and the web demo is simulated.")
            }
            HStack {
                Link("Try the live demo", destination: Product.demo)
                Spacer()
                Button("Connect a Mac") { onConnect() }
                Button("Continue") { onDone() }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
            }
        }.padding(28).frame(width: 560).background { AmbientBackground() }
    }
    private func point(_ symbol: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol).font(.title3).foregroundStyle(Color(hex: Brand.accentHex)).frame(width: 28)
            VStack(alignment: .leading, spacing: 2) { Text(title).font(.headline); Text(detail).foregroundStyle(.secondary) }
        }
    }
}
#endif

#if os(macOS)
struct IdentityCommands: Commands {
    @Environment(\.openWindow) private var openWindow
    var body: some Commands {
        CommandGroup(replacing: .appInfo) { Button("About Gryvia") { openWindow(id: "about") } }
        CommandGroup(replacing: .help) {
            Button("Welcome to Gryvia") { UserDefaults.standard.set(false, forKey: "welcomeSeen") }
            Link("Gryvia website", destination: Product.site)
            Link("Security policy", destination: Product.security)
        }
    }
}
#endif
