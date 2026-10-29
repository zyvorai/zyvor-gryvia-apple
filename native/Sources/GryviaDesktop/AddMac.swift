// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import AppKit
import GryviaCore

/// A freshly created join code. The plain code exists only in this value and on screen; the server keeps a hash.
struct NewJoin: Decodable { let id: String; let code: String; let node: String?; let expires: Double }
struct JoinRow: Decodable, Identifiable { let id: String; let node: String?; let state: String; let expires: Double }

/// "Add a Mac": create a single-use join code and show the command to run on the new Mac.
struct AddMacSheet: View {
    @Bindable var fleet: Fleet
    @Environment(\.dismiss) private var dismiss
    @State private var created: NewJoin?
    @State private var rows: [JoinRow] = []
    @State private var problem = ""
    @State private var nodesAtOpen: Set<String> = []

    /// `preview` pre-fills the created state for design snapshots only; it never talks to the server.
    init(fleet: Fleet, preview: NewJoin? = nil) { self.fleet = fleet; _created = State(initialValue: preview) }

    var command: String {
        guard let c = created else { return "" }
        return "python3 scripts/install-agent.py --binary /path/to/gryvia-agent --config agent.json --join \(fleet.server) --code \(c.code)"
    }
    var joined: [String] { (fleet.state?.nodes ?? []).map(\.id).filter { !nodesAtOpen.contains($0) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Add a Mac").font(.title2.bold())
            Text("Create a single-use code, then run the command on the new Mac. The code expires in 15 minutes and is shown only once; the server stores only a hash.")
                .font(.callout).foregroundStyle(.secondary)
            if let c = created {
                VStack(alignment: .leading, spacing: 8) {
                    Text(c.code).font(.system(.largeTitle, design: .monospaced).bold()).textSelection(.enabled)
                        .accessibilityLabel("Join code \(c.code.map(String.init).joined(separator: " "))")
                    Text(command).font(.system(.caption, design: .monospaced)).textSelection(.enabled).padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading).background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
                    HStack {
                        Button("Copy command", systemImage: "doc.on.doc") {
                            NSPasteboard.general.clearContents(); NSPasteboard.general.setString(command, forType: .string)
                        }
                        if joined.isEmpty {
                            Label("Waiting for the new Mac to appear…", systemImage: "hourglass").font(.caption).foregroundStyle(.secondary)
                        } else {
                            Label("Joined: \(joined.joined(separator: ", "))", systemImage: "checkmark.circle.fill").font(.caption).foregroundStyle(.green)
                        }
                    }
                }.padding(14).card()
            }
            if !problem.isEmpty { Text(problem).font(.caption).foregroundStyle(.red) }
            if !rows.isEmpty {
                Text("Recent codes").font(.headline)
                ForEach(rows.prefix(6)) { r in
                    HStack {
                        Text(r.id).font(.system(.caption, design: .monospaced))
                        Chip(text: r.node ?? "any node")
                        Chip(text: r.state, color: r.state == "used" ? .green : r.state == "open" ? .accentColor : .secondary)
                        Text(Date(timeIntervalSince1970: r.expires), style: .time).font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        if r.state == "open" { Button("Revoke") { Task { await revoke(r.id) } } }
                    }
                }
            }
            Spacer(minLength: 0)
            HStack {
                Button("Create join code", systemImage: "plus") { Task { await create() } }.buttonStyle(.borderedProminent)
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20).frame(width: 560, height: 480)
        .task {
            nodesAtOpen = Set((fleet.state?.nodes ?? []).map(\.id))
            while !Task.isCancelled { await load(); try? await Task.sleep(nanoseconds: 3_000_000_000) }
        }
    }

    func create() async {
        do {
            let data = try await fleet.api().request("api/enroll/tokens", body: ["ttl": 900])
            created = try JSONDecoder().decode(NewJoin.self, from: data); problem = ""; await load()
        } catch { problem = Fleet.hint(error) }
    }
    func load() async {
        guard let data = try? await fleet.api().request("api/enroll/tokens") else { return }
        rows = (try? JSONDecoder().decode([JoinRow].self, from: data)) ?? rows
        await fleet.refresh()      // so a Mac that just joined shows up here and in the fleet list
    }
    func revoke(_ id: String) async {
        do { _ = try await fleet.api().request("api/enroll/revoke", body: ["id": id]); await load() } catch { problem = Fleet.hint(error) }
    }
}
#endif
