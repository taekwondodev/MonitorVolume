# LAN transport and privacy research for the iPhone companion

Scope: native iOS companion, same Wi-Fi, three one-way commands (volume up, volume down, mute). The phone must not display volume or mute state. SDK scope requested is iOS 26/macOS 26; the existing Mac app supports macOS 15 and later. This is platform-documentation research, not a prototype or runtime certification.

## 1. Network.framework listener, Bonjour, lifecycle, Wi-Fi changes

**Facts.** Network.framework is Apple's direct API for protocols including TLS, TCP, and UDP; it exposes `NWListener` for incoming connections, `NWBrowser` for Bonjour discovery, and `NWConnection` for bidirectional connections. The framework has been available on iOS 12 and macOS 10.14, so the relevant APIs predate both deployment targets. (https://developer.apple.com/documentation/network)

`NWBrowser` discovers services using a service descriptor, reports state and result changes, and can be stopped with `cancel()`. (https://developer.apple.com/documentation/network/nwbrowser) An advertised Bonjour service type uses an application protocol label and transport label, for example `_myservice._tcp`; Apple says service types must be included in `NSBonjourServices` when registering or browsing specific Bonjour services. (https://developer.apple.com/documentation/bundleresources/information-property-list/nsbonjourservices ; https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

`NWConnection` is a bidirectional connection. The application therefore owns command framing, deciding when to close/reuse a connection, and treating a lost connection as uncertain delivery rather than proof a command was applied. Apple documents Network path monitoring and browser/connection state APIs, but does not promise that a listener or established connection survives an interface/address change unchanged. (https://developer.apple.com/documentation/network ; https://developer.apple.com/documentation/network/nwbrowser)

**Inference.** Use one explicit, versioned TCP Bonjour service type, a listener on the Mac and browser on iPhone, and reconnect/re-resolve upon browser changes, connection failure, or path changes. Commands should be small, self-contained, idempotent intent messages. Avoid reporting state back to the phone, consistent with settled scope. The user-visible pairing step must bind a discovered Mac to an authenticated key/identity, not trust a service name or network location alone.

**Uncertainty.** Apple API references establish API availability, not detailed behavior under every Wi-Fi roam/router configuration. Reconnection timing and sleep/wake behavior require device testing.

## 2. Authenticated encryption and TLS-PSK

**Facts.** Network.framework exposes TLS options via `NWProtocolTLS.Options`; Security protocol options expose functions to add a pre-shared key and identity hint, and to set TLS minimum/maximum versions. (https://developer.apple.com/documentation/network/nwprotocoltls/options ; https://developer.apple.com/documentation/network/security-options) The Network framework overview and TLS options page list support beginning at iOS 12/macOS 10.14, covering iOS 26, macOS 26, and macOS 15. (https://developer.apple.com/documentation/network ; https://developer.apple.com/documentation/network/nwprotocoltls/options)

**Important qualification.** The documentation proves the PSK configuration API exists, but the pages inspected do not state which TLS versions/ciphersuites support PSK, whether a particular PSK mode is negotiated by default, or guarantee compatibility between the precise iOS 26 and macOS 15 runtime combinations. Do not treat presence of `sec_protocol_options_add_pre_shared_key` as sufficient proof that TLS 1.3 PSK works on every target runtime. (https://developer.apple.com/documentation/network/security-options)

**Inference/recommendation.** Prefer authenticated TLS with per-pair credentials and validate the peer; Bonjour is discovery, not authentication. A PSK is a viable candidate to prototype, but confirm TLS 1.3 PSK negotiation on the minimum supported macOS 15 and iOS target, including key provisioning, rotation/revocation, and failed-authentication behavior. A certificate identity is another documented local-network TLS route. (https://developer.apple.com/documentation/network/creating-an-identity-for-local-network-tls)

## 3. Local Network privacy and macOS Firewall

**Facts.** Local Network privacy exists on iOS since iOS 14 and macOS since macOS 15. Apps that access local network resources need `NSLocalNetworkUsageDescription`; Bonjour registration, browsing, and resolution require Local Network access, and specific Bonjour service types belong in `NSBonjourServices`. (https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy ; https://developer.apple.com/documentation/bundleresources/information-property-list/nsbonjourservices ; https://developer.apple.com/documentation/bundleresources/information-property-list/nslocalnetworkusagedescription)

On iOS, outgoing TCP to a local address and Bonjour operations require the user's Local Network permission. If an iOS app first attempts a local-network operation in the background while permission is undetermined, the system denies it without showing the alert; a foreground attempt is required to present it. A real device is required to test this privacy behavior; the simulator does not support it. (https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

On macOS, the Network Privacy technote says ordinary programs should expect local-network operations to be blocked until the user grants Local Network permission; it explicitly auto-allows daemons, root programs, and command-line tools in Terminal/SSH, not ordinary GUI apps. `LSUIElement` is not an exemption documented by the technote. The technote says macOS tracks responsible code and presents permission UI as appropriate. (https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

Incoming TCP listener/accept does not itself require Local Network permission under the technote's TCP table. Advertising the Bonjour service does require it. The Mac app's Bonjour advertisement will thus need Local Network permission even if its inbound-only socket operation does not. (https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

**Firewall qualification.** Application Firewall is distinct from Local Network privacy. Apple documents managing firewall behavior in macOS settings and code-signing-related behavior, but available evidence here does not establish a deterministic prompt rule for this exact signed versus ad hoc `LSUIElement` app. Do not promise a prompt or absence of one: validate signed and ad hoc installs on the supported macOS versions with Firewall enabled. (https://support.apple.com/guide/mac-help/block-connections-to-your-mac-with-a-firewall-mh34041/mac)

**Inference.** The iOS app needs both keys and a clear permission explanation. Mac onboarding must explain its Local Network permission and handle denial without pretending the Mac is available. The project currently supports ad hoc signing, so Firewall identity/prompt behavior is an explicit release-test concern, not a documented assumption.

## 4. Control Center, Lock Screen widget, Action Button / App Intent

**Facts.** App Intents let app actions integrate with Siri, Shortcuts, widgets/controls, and the iPhone Action button. (https://developer.apple.com/documentation/appintents ; https://developer.apple.com/documentation/appintents/hardware-interactions) Apple's Local Network technote says a background iOS app with undetermined Local Network permission is denied the operation without an alert. (https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

**Inference.** An App Intent can provide an interaction surface, but it does not grant network permission or guarantee an execution context in which an operation needing a first-time permission prompt can succeed. The first pairing/permission grant must happen in the foreground app. After permission is granted, each desired surface still needs a real-device lifecycle test; current sources reviewed do not establish that a particular Control, Lock Screen widget, or Action Button invocation can always open/complete this local connection while the app is suspended. Design a graceful unavailable/bring-app-forward path, and do not make critical control depend on background execution.

## 5. Sleep, Bonjour Sleep Proxy, listener survival

**Facts.** The Bonjour sleep proxy is an Apple networking service concept intended to keep network services discoverable while a Mac sleeps, with wake-on-network-access dependent on Mac hardware, settings, and network support. Apple's general Bonjour overview describes Bonjour service discovery, but the sources examined do not make a guarantee that a third-party `NWListener` remains executing or that an arbitrary command wakes the Mac. (https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/NetServices/Introduction.html ; https://support.apple.com/guide/mac-help/set-sleep-and-wake-settings-mchle41a6ccd/mac)

**Inference.** Treat sleep as disconnection. The app cannot promise command execution while asleep. On wake, restart/revalidate listener advertisement and have the phone rediscover and reconnect. Sleep Proxy may preserve discoverability or wake a capable Mac under configured conditions, but must not be the protocol's correctness mechanism.

**Uncertainty.** No hardware-specific wake test was available. Screen/display sleep is distinct from system sleep; a sleeping display alone does not establish that the process or network listener is suspended.

## 6. Alternatives: Multipeer Connectivity and Bluetooth LE

**Facts.** Multipeer Connectivity discovers nearby services and supports message/stream/resource communication. iOS transports include infrastructure Wi-Fi, peer-to-peer Wi-Fi, and Bluetooth PAN; macOS uses infrastructure Wi-Fi, peer-to-peer Wi-Fi, and Ethernet. It uses Bonjour, so Local Network privacy and the declared service type still apply. When an app moves to background, Multipeer stops browsing/advertising and disconnects open sessions; foregrounding resumes browsing/advertising, but the app must reestablish sessions. (https://developer.apple.com/documentation/multipeerconnectivity ; https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

Core Bluetooth supports BLE central/peripheral communications and exposes characteristic permissions including encryption. It is available on both iOS and macOS. (https://developer.apple.com/documentation/corebluetooth ; https://developer.apple.com/documentation/corebluetooth/cbattributepermissions)

**Inference/recommendation.** Reject Multipeer Connectivity for this requirement because it adds peer/session abstraction and has the same Bonjour/privacy and background disconnect constraints, while the desired topology is a persistent Mac service discoverable over the existing Wi-Fi LAN. Reject BLE because the product specifically requires same-Wi-Fi control and already has a suitable IP transport; BLE adds a second radio protocol, pairing/characteristic lifecycle, and background constraints without solving Mac sleep. These are scope-fit judgments, not claims that either framework is technically incapable.

## Constraints the design must respect

1. Foreground pairing must establish the Mac's identity and durable per-peer authentication material; discovery by Bonjour alone is not trust.
2. Declare the Bonjour service type and Local Network usage explanation in both apps where applicable. First permission must be requested in foreground on iOS; Mac advertisement permission must be handled explicitly.
3. Keep the protocol strictly command-only. Do not send or render current volume, mute, acknowledgements containing state, or inferred state on iPhone.
4. Handle denied permission, absent service, Wi-Fi changes, connection loss, app suspension, and Mac sleep as unavailable/recoverable conditions. Rediscover and reconnect; never assume queued commands ran.
5. Provide immediate foreground controls as the dependable interaction surface. System controls/App Intents can be an optional convenience only after background execution and permission behavior is verified on physical devices.
6. Test TLS/PSK compatibility on iOS 26 and the minimum macOS 15 runtime; verify Firewall behavior separately for signed and ad hoc builds.

## Source index

- Network framework: https://developer.apple.com/documentation/network
- Local Network privacy TN3179: https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy
- Bonjour Info.plist key: https://developer.apple.com/documentation/bundleresources/information-property-list/nsbonjourservices
- Local network usage description: https://developer.apple.com/documentation/bundleresources/information-property-list/nslocalnetworkusagedescription
- TLS security options: https://developer.apple.com/documentation/network/security-options
- Local Network TLS identity: https://developer.apple.com/documentation/network/creating-an-identity-for-local-network-tls
- App Intents: https://developer.apple.com/documentation/appintents
- Multipeer Connectivity: https://developer.apple.com/documentation/multipeerconnectivity
- Core Bluetooth: https://developer.apple.com/documentation/corebluetooth
- macOS firewall guide: https://support.apple.com/guide/mac-help/block-connections-to-your-mac-with-a-firewall-mh34041/mac
- Bonjour overview archive: https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/NetServices/Introduction.html
- Mac sleep settings: https://support.apple.com/guide/mac-help/set-sleep-and-wake-settings-mchle41a6ccd/mac

## Coordinator verification

Checked against TN3179 (https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy, revision 2026-10-06):

- Confirmed: macOS local network privacy since macOS 15; listening for and accepting incoming TCP needs no Local Network access, while registering, browsing, and resolving Bonjour services do; an iOS app in the background with an undetermined privilege is denied without an alert.
- Correction to section 4: "In general, app extensions share the Local Network privilege state of their container app." Background extensions are denied only while the privilege is undetermined. After the user grants it in the foreground app, a widget or control extension is not blocked by local network privacy. Whether a given surface runs long enough to complete the connection remains a device test.
- Addition: local network privacy tracks a macOS program by its code signature, and Apple advises signing with an Apple-issued identity because ad hoc signing does not track reliably. The Mac app's current ad hoc fallback in `make build` would make the Local Network grant unreliable.
- Addition: specific service types listed in `NSBonjourServices` need no multicast entitlement; that entitlement applies only to arbitrary service types or browsing all types.
- Addition: a denied connection enters `NWConnection.State.waiting` with `NWPath.UnsatisfiedReason.localNetworkDenied`, and the system retries automatically after a later grant, so the iPhone can report "permission denied" distinctly from "Mac unreachable".
