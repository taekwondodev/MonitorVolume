import CoreAudio
import Dispatch
import Foundation
import MonitorTransport

package struct CoreAudioOutputRepository: ActiveAudioOutputReading {
    package init() {}

    package func resolveTarget() async throws(MonitorRepositoryError) -> AudioDisplayTarget? {
        let device = try defaultOutputDevice()
        let name = try stringProperty(kAudioObjectPropertyName, on: device)
        let manufacturer = try stringProperty(kAudioObjectPropertyManufacturer, on: device)
        let transport = try uint32Property(kAudioDevicePropertyTransportType, on: device)
        guard transport == kAudioDeviceTransportTypeDisplayPort else { return nil }
        var productID: UInt32 = 0
        var serial = [CChar](repeating: 0, count: 128)
        let status = name.withCString { namePointer in
            manufacturer.withCString { manufacturerPointer in
                MVDDCResolveAudioDisplay(
                    namePointer,
                    manufacturerPointer,
                    &productID,
                    &serial,
                    UInt32(serial.count)
                )
            }
        }
        switch status {
        case MVDDCStatusSuccess:
            let serialValue = Self.string(from: serial)
            return AudioDisplayTarget(
                identity: MonitorIdentity(
                    manufacturer: manufacturer,
                    productID: productID,
                    serial: serialValue.isEmpty ? nil : serialValue
                ),
                displayName: name
            )
        case MVDDCStatusTargetUnavailable:
            return nil
        case MVDDCStatusReadFailure:
            throw .readFailure
        default:
            throw .malformedResponse
        }
    }

    private static func string(from buffer: [CChar]) -> String {
        let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
        return String(decoding: bytes, as: UTF8.self)
    }

    package func observeDefaultOutputChanges(
        _ handler: @escaping @Sendable () -> Void
    ) throws(MonitorRepositoryError) -> ActiveAudioOutputObservation {
        try ActiveAudioOutputObservation(handler: handler)
    }

    private func defaultOutputDevice() throws(MonitorRepositoryError) -> AudioObjectID {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var device = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size,
            &device
        )
        guard status == noErr, device != kAudioObjectUnknown else {
            throw .readFailure
        }
        return device
    }

    private func stringProperty(
        _ selector: AudioObjectPropertySelector,
        on device: AudioObjectID
    ) throws(MonitorRepositoryError) -> String {
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectHasProperty(device, &address) else {
            throw .readFailure
        }
        var value: CFString = "" as CFString
        var size = UInt32(MemoryLayout<CFString>.size)
        let status = withUnsafeMutablePointer(to: &value) {
            AudioObjectGetPropertyData(device, &address, 0, nil, &size, $0)
        }
        guard status == noErr else {
            throw .readFailure
        }
        return value as String
    }

    private func uint32Property(
        _ selector: AudioObjectPropertySelector,
        on device: AudioObjectID
    ) throws(MonitorRepositoryError) -> UInt32 {
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectHasProperty(device, &address) else {
            throw .readFailure
        }
        var value: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &value)
        guard status == noErr else {
            throw .readFailure
        }
        return value
    }
}

package final class ActiveAudioOutputObservation: @unchecked Sendable {
    private let address: AudioObjectPropertyAddress
    private let queue: DispatchQueue
    private let listener: AudioObjectPropertyListenerBlock

    fileprivate init(handler: @escaping @Sendable () -> Void) throws(MonitorRepositoryError) {
        address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        queue = DispatchQueue(label: "dev.taekwondodev.MonitorVolume.default-output")
        listener = { _, _ in
            handler()
        }
        var registrationAddress = address
        let status = AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &registrationAddress,
            queue,
            listener
        )
        guard status == noErr else {
            throw .readFailure
        }
    }

    deinit {
        var removalAddress = address
        AudioObjectRemovePropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &removalAddress,
            queue,
            listener
        )
    }
}
