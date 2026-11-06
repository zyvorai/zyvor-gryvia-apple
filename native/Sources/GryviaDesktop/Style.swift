// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import AppKit
import GryviaCore

/// User-facing appearance keys stored in AppStorage / UserDefaults (never the access token).
enum AppearancePrefs {
    static let appearanceKey = "appearance"       // auto | light | dark
    static let windowStyleKey = "windowStyle"     // macos27 | glass
    static let reduceTransparencyKey = "reduceTransparency"
    static let accentKey = "accent"

    static var appearance: String { UserDefaults.standard.string(forKey: appearanceKey) ?? "auto" }
    static var windowStyle: String { UserDefaults.standard.string(forKey: windowStyleKey) ?? "macos27" }
    static var reduceTransparency: Bool {
        if UserDefaults.standard.object(forKey: reduceTransparencyKey) as? Bool == true { return true }
        return NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
    }
    static var accentName: String { UserDefaults.standard.string(forKey: accentKey) ?? "blue" }
    static var accentHex: UInt32 {
        Brand.accents.first { $0.name == accentName }?.hex ?? Brand.accentHex
    }
    static var colorScheme: ColorScheme? {
        switch appearance {
        case "light": return .light
        case "dark": return .dark
        default: return nil
        }
    }
}

/// One window chrome for the app and the snapshots: transparent title bar so the page background runs edge to edge.
enum WindowStyle {
    @MainActor static func apply(_ w: NSWindow) {
        w.titlebarAppearsTransparent = true
        w.styleMask.insert(.fullSizeContentView)
        let dark = w.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        let glass = AppearancePrefs.windowStyle == "glass" && !AppearancePrefs.reduceTransparency
        if dark {
            w.backgroundColor = glass ? NSColor.black.withAlphaComponent(0.92) : .black
        } else {
            w.backgroundColor = glass ? NSColor.windowBackgroundColor.withAlphaComponent(0.92) : .windowBackgroundColor
        }
    }
}

extension WindowStyle {
    /// SwiftUI gives the sidebar and title bar a system vibrancy layer that cannot be turned off from SwiftUI on macOS. In
    /// `macos27` (opaque) dark mode it shows as a grey slab beside the black page, so mask those layers. `glass` keeps blur.
    @MainActor static func flatten(_ w: NSWindow) {
        guard AppearancePrefs.windowStyle != "glass" || AppearancePrefs.reduceTransparency else { return }
        guard w.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua, let root = w.contentView?.superview else { return }
        func walk(_ v: NSView) {
            if let fx = v as? NSVisualEffectView { fx.maskImage = NSImage(size: NSSize(width: 1, height: 1)) }
            v.subviews.forEach(walk)
        }
        walk(root)
    }
    /// The views appear a moment after the window; flatten again as the layout settles.
    @MainActor static func flattenLater(_ w: NSWindow) {
        for delay in [0.2, 0.6, 1.5] { DispatchQueue.main.asyncAfter(deadline: .now() + delay) { apply(w); flatten(w) } }
    }
}

/// Adaptive colours. Dark: true black + glass cards + accent bloom. Light: soft paper + matching accent bloom.
enum Theme {
    private static func dynamic(dark: NSColor, light: NSColor) -> Color {
        Color(nsColor: NSColor(name: nil) { $0.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light })
    }
    /// Follows the Settings accent (and brand tokens), not a hard-coded blue.
    static var accent: Color { Color(hex: AppearancePrefs.accentHex) }
    static var accentGlow: Color { accent.mix(with: .white, by: 0.45) }
    static var surface: Color {
        if AppearancePrefs.reduceTransparency {
            return dynamic(dark: NSColor(white: 0.12, alpha: 1), light: NSColor(white: 0.97, alpha: 1))
        }
        return dynamic(dark: NSColor(white: 1, alpha: 0.055), light: NSColor(white: 1, alpha: 0.72))
    }
    static let hairline = dynamic(dark: NSColor(white: 1, alpha: 0.11), light: NSColor(white: 0, alpha: 0.08))
}

/// Page background: accent bloom in both schemes (softer in light); opaque when reduce-transparency is on.
struct AmbientBackground: View {
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let reduce = AppearancePrefs.reduceTransparency
        ZStack {
            if scheme == .dark {
                Color.black
                if !reduce {
                    RadialGradient(colors: [Theme.accent.opacity(0.26), .clear], center: .bottomLeading, startRadius: 0, endRadius: 720)
                    RadialGradient(colors: [Theme.accent.opacity(0.13), .clear], center: .topTrailing, startRadius: 0, endRadius: 520)
                }
            } else {
                Color(nsColor: NSColor(calibratedWhite: 0.96, alpha: 1))
                if !reduce {
                    RadialGradient(colors: [Theme.accent.opacity(0.14), .clear], center: .bottomLeading, startRadius: 0, endRadius: 640)
                    RadialGradient(colors: [Theme.accent.opacity(0.08), .clear], center: .topTrailing, startRadius: 0, endRadius: 480)
                }
            }
        }.ignoresSafeArea()
    }
}

/// Large figures: white-to-accent in dark; accent-tinted in light.
struct GlowText: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        if scheme == .dark {
            content.foregroundStyle(LinearGradient(colors: [.white, Theme.accentGlow], startPoint: .leading, endPoint: .trailing))
        } else {
            content.foregroundStyle(LinearGradient(colors: [Color.primary, Theme.accent], startPoint: .leading, endPoint: .trailing))
        }
    }
}
extension View { func glowText() -> some View { modifier(GlowText()) } }

/// 3px accent focus ring for keyboard users (UX contract).
struct AccentFocusRing: ViewModifier {
    @Environment(\.isFocused) private var focused
    func body(content: Content) -> some View {
        content.overlay {
            if focused {
                RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.accent, lineWidth: 3).padding(-3)
            }
        }
    }
}
extension View { func accentFocusRing() -> some View { modifier(AccentFocusRing()) } }

/// Mono, spaced, upper-case label above a title.
struct Eyebrow: View {
    let text: String
    var body: some View { Text(text.uppercased()).font(.system(size: 11, weight: .semibold, design: .monospaced)).tracking(1.6).foregroundStyle(Theme.accent) }
}

/// Card surface shared by the panes: concentric radii — panels 18 by default (contract: window 26 → panels 18 → controls 12 → small 8).
struct CardSurface: ViewModifier {
    var radius: CGFloat = 18
    func body(content: Content) -> some View {
        content
            .background(Theme.surface, in: .rect(cornerRadius: radius))
            .overlay(RoundedRectangle(cornerRadius: radius).strokeBorder(Theme.hairline))
    }
}
extension View { func card(radius: CGFloat = 18) -> some View { modifier(CardSurface(radius: radius)) } }

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

#if os(macOS)
/// Memory bar for a Mac: the filled part is what admission has *reserved* (bookkeeping), the tick is GPU memory this agent
/// has allocated. Neither is whole-system use. VoiceOver reads the same numbers.
struct CapacityBar: View {
    let reserved: Double, budget: Double
    var inUseGiB: Double?
    let label: String
    var body: some View {
        let total = max(budget, 0.001)
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(.quaternary)
                Capsule().fill(Color.accentColor).frame(width: g.size.width * min(1, reserved / total))
                if let u = inUseGiB {
                    Rectangle().fill(.primary).frame(width: 2).offset(x: g.size.width * min(1, u / total) - 1)
                }
            }.clipShape(Capsule())
        }
        .frame(height: 8)
        .accessibilityElement()
        .accessibilityLabel(label)
        .accessibilityValue(String(format: "%.1f of %.0f GiB reserved", reserved, budget) + (inUseGiB.map { String(format: ", %.1f GiB in use by this agent", $0) } ?? ""))
    }
}
#endif
