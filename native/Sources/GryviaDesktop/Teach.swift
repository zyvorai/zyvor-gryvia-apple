// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import GryviaCore

/// Empty state that says what the thing is and the one next step.
struct TeachingEmpty: View {
    let symbol: String, title: String, what: String, next: String
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: symbol).font(.system(size: 34)).foregroundStyle(LinearGradient(colors: [Theme.accentGlow, Theme.accent], startPoint: .top, endPoint: .bottom))
            Text(title).font(.system(.title3, design: .rounded, weight: .bold))
            Text(what).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Label(next, systemImage: "arrow.right.circle").font(.callout.weight(.medium)).foregroundStyle(Theme.accent)
        }
        .frame(maxWidth: 420).padding(28).frame(maxWidth: .infinity).card()
    }
}

/// Queued, admitted, running, finished: where the job is and when it got there.
struct JobTimeline: View {
    let job: Job
    private var steps: [(String, Double?, Bool)] {
        let finished = ["succeeded", "failed", "cancelled"].contains(job.state)
        return [("Queued", job.created, true), ("Admitted", job.started, job.started != nil), (finished ? job.state.capitalized : "Finished", job.finished, finished)]
    }
    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(steps.enumerated()), id: \.offset) { i, s in
                VStack(spacing: 4) {
                    Circle().fill(s.2 ? Theme.accent : Theme.hairline).frame(width: 10, height: 10)
                    Text(s.0).font(.caption.weight(s.2 ? .semibold : .regular)).foregroundStyle(s.2 ? .primary : .secondary)
                    if let t = s.1, s.2 { Text(Date(timeIntervalSince1970: t), style: .time).font(.caption2.monospacedDigit()).foregroundStyle(.secondary) } else { Text(" ").font(.caption2) }
                }.frame(maxWidth: .infinity)
                if i < steps.count - 1 { Rectangle().fill(steps[i + 1].2 ? Theme.accent : Theme.hairline).frame(height: 2).frame(maxWidth: 40).offset(y: -12) }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// ⌘K: jump to a pane or run an action.
struct PaletteCommand: Identifiable { let id = UUID(); let title: String; let symbol: String; let run: @MainActor () -> Void }

struct PaletteView: View {
    let commands: [PaletteCommand]
    var dismiss: () -> Void
    @State private var query = ""
    private var matches: [PaletteCommand] { query.isEmpty ? commands : commands.filter { $0.title.localizedCaseInsensitiveContains(query) } }
    var body: some View {
        VStack(spacing: 0) {
            TextField("Type a command or a pane name", text: $query).textFieldStyle(.plain).font(.title3).padding(16)
                .onSubmit { if let c = matches.first { dismiss(); c.run() } }
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(matches) { c in
                        Button { dismiss(); c.run() } label: {
                            Label(c.title, systemImage: c.symbol).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 12).padding(.vertical, 7).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                    }
                    if matches.isEmpty { Text("No match").foregroundStyle(.secondary).padding(12) }
                }.padding(8)
            }.frame(height: 260)
        }.frame(width: 480).background { AmbientBackground() }
    }
}
#endif
