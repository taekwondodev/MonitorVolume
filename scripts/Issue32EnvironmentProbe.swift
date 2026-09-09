import Foundation

let state: String
switch ProcessInfo.processInfo.thermalState {
case .nominal:
    state = "nominal"
case .fair:
    state = "fair"
case .serious:
    state = "serious"
case .critical:
    state = "critical"
@unknown default:
    state = "unknown"
}

let payload = ["thermalState": state]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data("\n".utf8))
