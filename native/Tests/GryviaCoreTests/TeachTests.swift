// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
import XCTest
@testable import GryviaCore

final class TeachTests: XCTestCase {
    func testEverySchedulerReasonHasAnExplanation() {
        // reasons emitted by server/core.py admission and lifecycle
        for reason in ["node memory reservation budget", "tenant memory quota", "tenant quota", "waiting for exclusive worker", "waiting for dependency",
                       "draining", "thermal gate", "insufficient memory headroom", "owner returned; will resume when the Mac is idle",
                       "lease expired; old worker must stop", "job timeout"] {
            XCTAssertNotNil(ReasonText.explain(reason), reason)
        }
    }
    func testUnknownReasonFallsBackToNil() { XCTAssertNil(ReasonText.explain("something new")) }
    func testExplanationIsCaseInsensitive() { XCTAssertNotNil(ReasonText.explain("Draining")) }
    func testGlossaryAliasesResolve() {
        XCTAssertEqual(Glossary.entry(for: "reserved")?.term, "reservation")
        XCTAssertEqual(Glossary.entry(for: "Running")?.term, "running")
        XCTAssertNil(Glossary.entry(for: "completed"))
    }
    func testGlossaryStatesReservationIsBookkeeping() {
        XCTAssertTrue(Glossary.entries["reservation"]!.contains("bookkeeping"))
    }
}
