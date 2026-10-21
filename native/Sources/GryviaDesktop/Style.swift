// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI

/// Card surface shared by the panes: same radius, fill and hairline as the Live and Overview cards.
struct CardSurface: ViewModifier {
    var radius: CGFloat = 14
    func body(content: Content) -> some View {
        content
            .background(Color(nsColor: .controlBackgroundColor), in: .rect(cornerRadius: radius))
            .overlay(RoundedRectangle(cornerRadius: radius).strokeBorder(Color(nsColor: .separatorColor).opacity(0.7)))
    }
}
extension View { func card(radius: CGFloat = 14) -> some View { modifier(CardSurface(radius: radius)) } }

/// Title, one-line explanation and optional trailing summary, used at the top of the list panes.
struct PaneHeader: View {
    let title: String, subtitle: String
    var trailing: String = ""
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.system(.title2, design: .rounded, weight: .bold))
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
#endif
