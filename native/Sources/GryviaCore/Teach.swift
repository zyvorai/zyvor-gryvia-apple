// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
import Foundation

/// Plain-language definitions, shown from the hero chips. Wording follows docs/GETTING-STARTED.md and the Guide pane.
public enum Glossary {
    public static let entries: [String: String] = [
        "reservation": "Memory a job sets aside on a Mac. It is admission bookkeeping so jobs do not overload a machine, not a live GPU meter.",
        "drain": "Stop sending new jobs to a Mac for maintenance. Running jobs finish; Resume undoes it.",
        "priority": "0 to 100. Higher goes first when jobs are waiting; fairness weights still apply between tenants.",
        "unified memory": "Apple Silicon shares one memory pool between CPU and GPU, so a Mac's budget covers both.",
        "admission": "The check that decides whether a queued job fits a Mac's memory budget and its tenant's quota right now.",
        "queued": "Waiting for admission. Open the job to see why.",
        "running": "Admitted and executing on a Mac.",
    ]
    /// Chip labels map onto the term they explain.
    public static func entry(for label: String) -> (term: String, text: String)? {
        let key = label.lowercased()
        let alias = ["reserved": "reservation", "memory reserved": "reservation", "budget": "unified memory"][key] ?? key
        return entries[alias].map { (alias, $0) }
    }
}

/// Scheduler reasons (server/core.py) in words a person can act on.
public enum ReasonText {
    public static func explain(_ reason: String) -> String? {
        let r = reason.lowercased()
        let table: [(String, String)] = [
            ("node memory reservation budget", "Every Mac that could run this is at its memory budget. It starts when a running job finishes or a Mac with room appears."),
            ("tenant memory quota", "This tenant has used its memory allowance. It starts when one of the tenant's jobs finishes, or an admin raises the quota."),
            ("tenant quota", "This tenant has used its memory allowance. It starts when one of the tenant's jobs finishes, or an admin raises the quota."),
            ("waiting for exclusive worker", "This job needs a Mac to itself, and every candidate is busy."),
            ("waiting for dependency", "A job it depends on has not succeeded yet."),
            ("draining", "The Mac is draining for maintenance and takes no new jobs. Resume it under Fleet."),
            ("thermal gate", "The Mac is running hot, so new work is held back until it cools."),
            ("insufficient memory headroom", "The Mac does not currently have enough free unified memory for this job."),
            ("owner returned", "The Mac's owner came back, so the job yielded. It resumes when the Mac is idle again."),
            ("lease expired", "The worker stopped reporting, so the job was returned to the queue."),
            ("job timeout", "The job ran past its time limit and was stopped."),
        ]
        return table.first { r.contains($0.0) }?.1
    }
}

