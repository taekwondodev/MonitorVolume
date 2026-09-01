// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "ProArtVolume",
    platforms: [
        .macOS(.v15)
    ],
    products: [
        .executable(name: "ProArtVolume", targets: ["ProArtVolume"])
    ],
    targets: [
        .executableTarget(name: "ProArtVolume"),
        .testTarget(
            name: "ProArtVolumeTests",
            dependencies: ["ProArtVolume"]
        )
    ]
)
