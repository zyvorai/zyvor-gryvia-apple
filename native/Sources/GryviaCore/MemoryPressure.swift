// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
import Foundation
#if os(macOS)
import Darwin
#endif

/// OS pressure plus an estimate of reclaimable RAM. Neither value is per-job GPU memory.
public final class MemoryPressureMonitor: @unchecked Sendable {
    public static let shared = MemoryPressureMonitor()
    private let lock = NSLock()
    private var level = "unknown"
    #if os(macOS)
    private var source: DispatchSourceMemoryPressure?
    #endif

    private init() {
        #if os(macOS)
        let source = DispatchSource.makeMemoryPressureSource(eventMask: [.normal, .warning, .critical], queue: DispatchQueue(label: "gryvia.memory-pressure"))
        self.source = source
        source.setEventHandler { [weak self] in
            guard let self, let data = self.source?.data else { return }
            self.lock.lock()
            self.level = Self.label(critical: data.contains(.critical), warning: data.contains(.warning))
            self.lock.unlock()
        }
        source.resume()
        #endif
    }

    public static func label(critical: Bool, warning: Bool) -> String {
        critical ? "critical" : warning ? "warning" : "normal"
    }

    public func report() -> [String: Any] {
        lock.lock(); let pressure = level; lock.unlock()
        var out: [String: Any] = ["pressure": pressure, "memoryHeadroomGiB": 1.0]
        #if os(macOS)
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
        let status = withUnsafeMutablePointer(to: &stats) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { p in
                host_statistics64(mach_host_self(), HOST_VM_INFO64, p, &count)
            }
        }
        // host_page_size, not the vm_kernel_page_size global, which Swift 6 rejects as shared mutable state.
        var pageSize: vm_size_t = 0
        if status == KERN_SUCCESS, host_page_size(mach_host_self(), &pageSize) == KERN_SUCCESS {
            // Free + inactive is an estimate of available/reclaimable memory, not a reservation guarantee.
            let bytes = (Double(stats.free_count) + Double(stats.inactive_count)) * Double(pageSize)
            out["availableGiB"] = bytes / pow(1024, 3)
        }
        #endif
        return out
    }
}
