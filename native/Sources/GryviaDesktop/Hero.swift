// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
#if os(macOS)
import SwiftUI
import Charts
import GryviaCore

/// Circular gauge. `fraction` is clamped to 0...1; the caption says what is measured (never imply more than it is).
struct RingGauge: View {
    let fraction: Double
    let label: String
    let caption: String
    var size: CGFloat = 120
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var clamped: Double { min(max(fraction, 0), 1) }
    var body: some View {
        ZStack {
            Circle().stroke(Theme.hairline, lineWidth: size * 0.09)
            Circle().trim(from: 0, to: clamped)
                .stroke(AngularGradient(colors: [Theme.accent.opacity(0.55), Theme.accentGlow], center: .center, startAngle: .degrees(0), endAngle: .degrees(360 * max(clamped, 0.01))),
                        style: StrokeStyle(lineWidth: size * 0.09, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: Theme.accent.opacity(0.55), radius: size * 0.07)
                .animation(reduceMotion ? nil : .smooth(duration: 0.8), value: clamped)
            VStack(spacing: 0) {
                Text(label).font(.system(size: size * 0.24, weight: .bold, design: .rounded)).monospacedDigit().glowText()
                Text(caption).font(.system(size: size * 0.095)).foregroundStyle(.secondary)
            }
        }
        .frame(width: size, height: size).padding(size * 0.05)
        .accessibilityElement().accessibilityLabel(caption).accessibilityValue(label)
    }
}

/// Axis-free area chart of a short series (0...max).
struct Sparkline: View {
    let values: [Double]
    var height: CGFloat = 44
    var body: some View {
        if values.count > 1 {
            Chart(Array(values.enumerated()), id: \.offset) { i, v in
                AreaMark(x: .value("t", i), y: .value("v", v)).foregroundStyle(LinearGradient(colors: [Theme.accent.opacity(0.35), .clear], startPoint: .top, endPoint: .bottom))
                LineMark(x: .value("t", i), y: .value("v", v)).foregroundStyle(Theme.accentGlow).lineStyle(StrokeStyle(lineWidth: 1.6, lineJoin: .round))
            }
            .chartXAxis(.hidden).chartYAxis(.hidden).chartYScale(domain: 0...max(values.max() ?? 1, 1))
            .frame(height: height)
            .accessibilityLabel("Recent trend").accessibilityValue(String(format: "latest %.0f", values.last ?? 0))
        }
    }
}

/// Pane header with a big figure, one honest sentence, stat chips, and an optional ring and trend.
struct HeroHeader: View {
    let eyebrow: String
    let figure: String
    let unit: String
    let sentence: String
    var chips: [(String, String)] = []          // (value, label)
    var ring: (fraction: Double, label: String, caption: String)? = nil
    var trend: [Double] = []
    var body: some View {
        HStack(alignment: .center, spacing: 24) {
            VStack(alignment: .leading, spacing: 8) {
                Eyebrow(text: eyebrow)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(figure).font(.system(size: 60, weight: .bold, design: .rounded)).monospacedDigit().glowText().contentTransition(.numericText())
                    Text(unit).font(.system(.title2, design: .rounded, weight: .semibold)).foregroundStyle(.secondary)
                }
                Text(sentence).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                if !chips.isEmpty {
                    HStack(spacing: 18) {
                        ForEach(chips, id: \.1) { c in ChipView(value: c.0, label: c.1) }
                    }
                }
                if trend.count > 1 { Sparkline(values: trend).frame(maxWidth: 360) }
            }
            Spacer(minLength: 12)
            if let ring { RingGauge(fraction: ring.fraction, label: ring.label, caption: ring.caption) }
        }
        .padding(.vertical, 6)
    }
}

/// A figure and its label; the label opens a plain-language definition when the Glossary has one.
struct ChipView: View {
    let value: String, label: String
    @State private var open = false
    var body: some View {
        let entry = Glossary.entry(for: label)
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(value).font(.callout.weight(.semibold).monospacedDigit())
            if let entry {
                Button { open = true } label: { Text(label).font(.callout).foregroundStyle(.secondary).underline(true, pattern: .dot) }
                    .buttonStyle(.plain).help("What does “\(label)” mean?")
                    .popover(isPresented: $open) { VStack(alignment: .leading, spacing: 4) { Text(entry.term.capitalized).font(.headline); Text(entry.text).foregroundStyle(.secondary) }.padding(14).frame(width: 260) }
            } else { Text(label).font(.callout).foregroundStyle(.secondary) }
        }
    }
}

/// Mean utilisation per sample across Macs (device-wide GPU %, as macOS reports it).
func fleetUtilSeries(_ telemetry: [String: [TelemetrySample]], nodes: [Node]) -> [Double] {
    let series = nodes.filter(\.online).compactMap { telemetry[$0.id]?.map(\.util) }.filter { !$0.isEmpty }
    guard let n = series.map(\.count).min() else { return [] }
    return (0..<n).map { i in series.map { $0[$0.count - n + i] }.reduce(0, +) / Double(series.count) }
}

/// Calm "nothing needs attention" illustration for the Alerts pane.
struct AllClear: View {
    var body: some View {
        VStack(spacing: 14) {
            ZStack {
                Circle().fill(Theme.accent.opacity(0.12)).frame(width: 150, height: 150).blur(radius: 18)
                Circle().stroke(Theme.hairline, lineWidth: 1).frame(width: 110, height: 110)
                Image(systemName: "checkmark.shield.fill").font(.system(size: 52)).foregroundStyle(LinearGradient(colors: [Theme.accentGlow, Theme.accent], startPoint: .top, endPoint: .bottom))
            }
            Text("All clear").font(.system(.title, design: .rounded, weight: .bold)).glowText()
            Text("No offline Macs, thermal limits or failed jobs. Alerts appear here the moment one happens.").foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: 360)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).padding(40)
    }
}
#endif
