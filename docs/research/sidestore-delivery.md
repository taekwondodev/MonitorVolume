# SideStore delivery research

Scope: deliver a future native iOS companion from this repository to the requester's iPhone 14 Pro through their existing SideStore installation, using a free Apple ID. This is research, not an implementation. The related build/project-layout report is `docs/research/ios-companion-build-and-signing.md` on `research/ios-companion-build-and-signing`; this report does not repeat its project architecture conclusions.

## Facts

### 1. Artifact, packaging, and signing

SideStore says it can install any `.ipa`; its README describes using the user's Apple ID, signing apps with the personal development certificate, and refreshing them to avoid the ordinary seven-day development signing expiry. Therefore the intended handoff artifact is an IPA containing an iOS application bundle, not this repository's existing macOS executable or an `.app` intended for direct installation. (https://sidestore.io/; https://github.com/SideStore/SideStore/blob/develop/README.md)

An IPA is the packaged app archive; a project/scheme is required to build the future iOS target. The repository currently has no iOS Xcode project: see the prior report `docs/research/ios-companion-build-and-signing.md`, which records the package platforms and existing command surface. An example command shape, once an iOS scheme exists, is:

```sh
xcodebuild -project Companion.xcodeproj -scheme Companion \
  -configuration Release -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  -derivedDataPath build/ios CODE_SIGNING_ALLOWED=NO build
```

This is a candidate shape, not a tested repository command. It produces build products, not automatically a SideStore-ready IPA. Export/package the built `.app` into an IPA separately, or use an archive/export path configured for unsigned distribution as supported by the selected Xcode version. The SideStore documentation inspected here does not specify all accepted IPA internals or state that it removes arbitrary existing signatures/provisioning profiles. Do not rely on a claim that SideStore rewrites bundle identifier, team prefix, entitlements, or profiles until confirmed against the exact SideStore app version/source. Its README does establish re-signing with the user's personal development certificate, but not those detailed rewrite rules.

### 2. Free-account limits

The retrieved official SideStore README states that signing uses the user's personal development certificate and that apps have a normal seven-day development period. It does not establish the numeric SideStore limits for active apps, App IDs, or extensions. Apple's Personal Team limits in the prior report are not interchangeable with SideStore's own app behavior. In particular, extension counting and whether SideStore itself consumes an active-app slot remain unverified in the official sources inspected here. Treat these as constraints to verify in the installed SideStore version before deciding to add app extensions.

### 3. Capabilities and persistence

The SideStore README inspected here does not document the survival or rewriting of Keychain access groups, App Groups, local-network privacy usage descriptions, or Bonjour service declarations. No claim that Keychain data or the iOS Local Network permission persists across refresh or an updated IPA is established by that source. Keep the iOS companion's interaction surface and pairing design independent of assumptions about cross-refresh credential persistence until tested or supported by SideStore source/documentation. App Groups also require a matching signed entitlement across app and extension; whether SideStore can preserve the needed group entitlement is unresolved.

### 4. Delivery from Mac to SideStore

The SideStore website explicitly advertises installation of any IPA, which supports importing a locally transferred IPA as the basic route. The inspected page does not document AirDrop, Files import steps, source-repository metadata requirements, or a Mac-to-phone transfer protocol. SideStore README says it downloads and updates apps through SideStore, but that does not by itself establish how to publish a custom app source or the metadata schema. Therefore a direct IPA transfer (for example via Files) is the simplest candidate, not a fully verified step-by-step official procedure; a SideStore/AltStore source should not be selected until its required feed format and hosting are confirmed from source/docs.

### 5. Repository command shape

The current `Makefile` commands are Mac-focused: `make build` builds, signs, installs, and launches the macOS app, while `make clean` only cleans SwiftPM artifacts (`Makefile:1-32`, `README.md:27-33`). A future iOS artifact command should be separate, for example `make ios-ipa`, and should invoke a checked-in Xcode project/scheme using `xcodebuild`, then package the resulting app into a predictable `.ipa` path. Do not change the semantics of `make build`. The exact signing and export flags depend on the chosen IPA packaging workflow and must be validated against Xcode 27 before implementation.

## Inferences and constraints for product decisions

- The requested delivery route is local sideloading, not App Store distribution: SideStore's published description directly supports user-Apple-ID installation and refresh. (https://github.com/SideStore/SideStore/blob/develop/README.md)
- The app should initially avoid extensions unless a needed feature justifies their signing/App ID budget, because the relevant SideStore limits and entitlement behavior were not established in this research.
- Pairing should not assume a Keychain item will remain usable after an identifier/team rewrite or refresh. The server/client identity and recovery UX need to tolerate reinstallation or credential loss until persistence is proven.
- Local-network access still needs the iOS app's privacy declarations (`NSLocalNetworkUsageDescription`, `NSBonjourServices`) for Bonjour/TCP discovery/use; whether SideStore preserves these is an implementation verification item, not a fact proven by the retrieved SideStore README.

## Hypotheses and unresolved evidence

- **Hypothesis:** SideStore accepts an unsigned IPA and supplies the signing/provisioning material itself. The site says “Install any .ipa” and the README says SideStore resigns apps, but exact input-signature requirements were not established. Check the app's IPA import/signing pipeline at a named SideStore commit and test a locally built unsigned IPA.
- **Hypothesis:** an updated IPA with the same effective identifier retains app container data and privacy grants. Neither persistence behavior was established by the inspected SideStore documentation. Test refresh and update on a spare app/device, and inspect the effective bundle identifier, entitlements, profile, Keychain access, and Local Network prompt state before/after.
- Verify numeric free-account active-app and App ID limits, whether SideStore counts itself, and how extension targets count, from current AltSign/SideStore source or official docs before committing to an extension-based UI.
- Verify direct Files/AirDrop import instructions and custom source feed requirements from current official documentation or source before documenting them as supported workflows.

## Sources and limits

- SideStore website, “Install any .ipa”: https://sidestore.io/ (retrieved 2026-10-15).
- SideStore README, current `develop` branch: https://github.com/SideStore/SideStore/blob/develop/README.md (retrieved 2026-10-15). The source says SideStore uses a personal development certificate and periodically refreshes apps; it does not answer all five detailed questions.
- Related repository evidence: `docs/research/ios-companion-build-and-signing.md` on branch `research/ios-companion-build-and-signing`; local `Makefile:1-32` and `README.md:27-33`.
- AltStore/AltSign source, exact source revision, and detailed entitlement/capability handling were not inspected. Numeric limits and persistence claims are intentionally left unresolved rather than inferred from community reports or from Apple's Personal Team limits.

## Coordinator verification

Sources checked by the coordinator on 2026-10-15: the SideStore FAQ (https://docs.sidestore.io/docs/faq), the AltStore App IDs page (https://faq.altstore.io/altstore-classic/app-ids), the AltStore source format (https://faq.altstore.io/developers/make-a-source), and SideStore source at commit `12ff39c6b6c0ccd8180f0834a893a4bbaf7bcd31` (develop, 2026-10-13). These resolve most of the gaps above.

**Facts.**

- Limits: with a free Apple Account, SideStore installs at most 3 apps at a time including itself, and at most 10 App IDs per week (SideStore FAQ). Every app extension needs its own App ID, and each App ID expires after one week (AltStore App IDs page; SideStore is an AltStore fork per its FAQ). A companion with one widget or control extension therefore costs 2 App IDs and 1 active app slot.
- Developer changes: "Your apps shouldn't need any modification to work with SideStore" (SideStore FAQ).
- Bundle identifier rewrite: for a new install, the App ID registered is `<bundle identifier>.<team identifier>` (https://github.com/SideStore/SideStore/blob/12ff39c6b6c0ccd8180f0834a893a4bbaf7bcd31/SideStore/Core/Operations/PipelineOperations/FetchProvisioningProfilesOperation.swift#L147-L150); an already installed app keeps its previous resigned identifier when the team matches (same file, L118-L136). Extension identifiers are rewritten by replacing the parent prefix (same file, L42, L76), and extension identifiers must start with the parent identifier plus a dot (same file, L157-L158). The new identifier is written into `CFBundleIdentifier` in each bundle's Info.plist (https://github.com/SideStore/SideStore/blob/12ff39c6b6c0ccd8180f0834a893a4bbaf7bcd31/SideStore/Core/Operations/PipelineOperations/ResignAppOperation.swift#L132-L133).
- App Groups rewrite: requested groups are registered with the team identifier appended, `<group>.<team identifier>` (FetchProvisioningProfilesOperation.swift L409, L451). Code that hardcodes the original group identifier will not find the signed group.
- Info.plist handling: the resign step rewrites `CFBundleIdentifier`, background task identifiers, URL schemes, exported UTIs, and file provider groups, and removes `DTXcode` keys (ResignAppOperation.swift L85-L178). It does not touch `NSLocalNetworkUsageDescription` or `NSBonjourServices`.
- Data persistence: installing the same or an updated IPA over an existing app keeps its data intact (SideStore FAQ, "Can I transfer my AltStore/Sideloadly apps?"). Because the resigned identifier and team stay stable across refresh (FetchProvisioningProfilesOperation.swift L118-L136), the app's default Keychain access group stays stable as well.
- Source distribution: a source is a self-hosted JSON file listing apps by bundle identifier with downloadable versions (AltStore "Make a Source"). It is optional; direct IPA installation needs no source.

**Inferences.**

- Pairing secrets kept in the app's default Keychain access group should survive the 7-day refresh and updated installs. Sharing them with an extension needs an App Group or Keychain sharing entitlement whose identifier must be read at runtime, because SideStore appends the team identifier.
- With SideStore occupying one of the three slots, the companion uses a second slot, leaving one for any other sideloaded app the requester uses. Each extension adds weekly App ID pressure.

**Hypotheses still open.**

- SideStore accepts an IPA built with `CODE_SIGNING_ALLOWED=NO` and packaged as `Payload/<App>.app` in a zip. The import pipeline re-signs everything, but no local build was attempted; verify during implementation with the first `make ios-ipa` artifact.
- The iOS Local Network grant survives refresh and updates. No source states it; iOS keys privacy grants per app, and the bundle identifier is stable, but this needs a device observation.
