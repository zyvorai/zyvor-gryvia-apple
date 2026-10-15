// SPDX-License-Identifier: BUSL-1.1
// Copyright © 2026 Zyvor AI Labs Private Limited
import Foundation

private final class NoWorkerRedirect: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

/// Poll only while this agent owns the serve lease. Platform tokens never go to the model server.
public enum InferenceRelay {
    public static func run(api: API, job: Claim) async {
        let session = URLSession(configuration: .ephemeral, delegate: NoWorkerRedirect(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        while !Task.isCancelled {
            do {
                let data = try await api.request("api/agent/relay-poll", body: ["id": job.id, "lease": job.lease])
                guard let envelope = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let item = envelope["request"] as? [String: Any] else {
                    try await Task.sleep(nanoseconds: 250_000_000)
                    continue
                }
                try await forward(item, api: api, job: job, session: session)
            } catch {
                if Task.isCancelled { return }
                try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
    }

    private static func forward(_ item: [String: Any], api: API, job: Claim, session: URLSession) async throws {
        guard let id = item["id"] as? String, let endpoint = item["endpoint"] as? String,
              let url = URL(string: endpoint), url.scheme == "http", url.host == "127.0.0.1", url.port != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/", let body = item["body"] as? [String: Any] else {
            throw GryviaError.invalid("Invalid local relay request")
        }
        var sequence = 0
        do {
            var request = URLRequest(url: url.appendingPathComponent("v1/chat/completions"))
            request.httpMethod = "POST"; request.timeoutInterval = 180
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (bytes, response) = try await session.bytes(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw GryviaError.invalid("Local inference failed")
            }
            var buffer = Data(); var total = 0
            for try await byte in bytes {
                try Task.checkCancellation()
                buffer.append(byte); total += 1
                guard total <= 4 * 1024 * 1024 else { throw GryviaError.invalid("Response too large") }
                if buffer.count >= 8192 || (body["stream"] as? Bool == true && buffer.suffix(2) == Data([10, 10])) {
                    try await push(buffer, id: id, sequence: sequence, done: false, api: api, job: job)
                    sequence += 1; buffer.removeAll(keepingCapacity: true)
                }
            }
            try await push(buffer, id: id, sequence: sequence, done: true, api: api, job: job)
        } catch {
            // Do not forward worker logs, URLs, headers or secrets in error messages.
            _ = try? await api.request("api/agent/relay-push", body: ["id": job.id, "lease": job.lease,
                "request": id, "seq": sequence, "error": "local inference failed", "done": true])
            throw error
        }
    }

    private static func push(_ data: Data, id: String, sequence: Int, done: Bool, api: API, job: Claim) async throws {
        _ = try await api.request("api/agent/relay-push", body: ["id": job.id, "lease": job.lease,
            "request": id, "seq": sequence, "data": data.base64EncodedString(), "done": done])
    }
}
