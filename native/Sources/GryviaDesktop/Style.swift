// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import AppKit
import GryviaCore

/// Adaptive colours. Dark follows the Zyvor product look: true black, translucent glass cards, a faint blue bloom.
enum Theme {
    private static func dynamic(dark: NSColor, light: NSColor) -> Color {
        Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light })
    }
    static let surface = dynamic(dark: NSColor(white: 1, alpha: 0.055), light: .controlBackgroundColor)
    static let hairline = dynamic(dark: NSColor(white: 1, alpha: 0.11), light: NSColor.separatorColor)
    static let accent = Color(hex: Brand.accentHex)
    /// Bright end of the dark-mode numeral gradient (accent lightened toward white).
    static let accentGlow = Color(hex: Brand.accentHex).mix(with: .white, by: 0.45)
}

/// Page background: plain in light; in dark, black with a blue bloom from the lower left and a softer one top right.
struct AmbientBackground: View {
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        if scheme == .dark {
            ZStack {
                Color.black
                RadialGradient(colors: [Theme.accent.opacity(0.26), .clear], center: .bottomLeading, startRadius: 0, endRadius: 720)
                RadialGradient(colors: [Theme.accent.opacity(0.13), .clear], center: .topTrailing, startRadius: 0, endRadius: 520)
            }.ignoresSafeArea()
        } else {
            Color(nsColor: .windowBackgroundColor).ignoresSafeArea()
        }
    }
}

/// Large figures: white-to-blue in dark (as on the product site), plain in light.
struct GlowText: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        if scheme == .dark { content.foregroundStyle(LinearGradient(colors: [.white, Theme.accentGlow], startPoint: .leading, endPoint: .trailing)) }
        else { content }
    }
}
extension View { func glowText() -> some View { modifier(GlowText()) } }

/// Mono, spaced, upper-case label above a title.
struct Eyebrow: View {
    let text: String
    var body: some View { Text(text.uppercased()).font(.system(size: 11, weight: .semibold, design: .monospaced)).tracking(1.6).foregroundStyle(Theme.accent) }
}

/// Card surface shared by the panes: same radius, fill and hairline as the Live and Overview cards.
struct CardSurface: ViewModifier {
    var radius: CGFloat = 14
    func body(content: Content) -> some View {
        content
            .background(Theme.surface, in: .rect(cornerRadius: radius))
            .overlay(RoundedRectangle(cornerRadius: radius).strokeBorder(Theme.hairline))
    }
}
extension View { func card(radius: CGFloat = 14) -> some View { modifier(CardSurface(radius: radius)) } }

/// Title, one-line explanation and optional trailing summary, used at the top of the list panes.
struct PaneHeader: View {
    let title: String
    var eyebrow: String = ""
    let subtitle: String
    var trailing: String = ""
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 3) {
                if !eyebrow.isEmpty { Eyebrow(text: eyebrow) }
                Text(title).font(.system(.largeTitle, design: .rounded, weight: .bold)).glowText()
                Text(subtitle).font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
            if !trailing.isEmpty { Text(trailing).font(.callout.monospacedDigit()).foregroundStyle(.secondary) }
        }
    }
}

/// Small rounded label, used for runtimes, thermal state and similar facts.
struct Chip: View {
    let text: String
    var color: Color = .secondary
    var body: some View {
        Text(text).font(.caption.weight(.medium)).foregroundStyle(color)
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(color.opacity(0.14), in: .capsule)
    }
}

extension Color {
    /// Linear mix in sRGB; good enough for a highlight colour.
    func mix(with other: Color, by amount: Double) -> Color {
        let a = NSColor(self).usingColorSpace(.sRGB) ?? .white, b = NSColor(other).usingColorSpace(.sRGB) ?? .white
        return Color(red: a.redComponent + (b.redComponent - a.redComponent) * amount, green: a.greenComponent + (b.greenComponent - a.greenComponent) * amount, blue: a.blueComponent + (b.blueComponent - a.blueComponent) * amount)
    }
}
#endif
