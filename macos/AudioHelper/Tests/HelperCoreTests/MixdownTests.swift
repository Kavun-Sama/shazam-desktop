import XCTest

@testable import HelperCore

final class MixdownTests: XCTestCase {
    func testInterleavedStereoIsAveraged() {
        let samples: [Float] = [1, 0, 0.5, 0.5, -1, 1]
        let mono = samples.withUnsafeBufferPointer { Mixdown.interleaved($0, channels: 2) }
        XCTAssertEqual(mono, [0.5, 0.5, 0])
    }

    func testInterleavedMonoIsPassedThrough() {
        let samples: [Float] = [0.1, -0.2, 0.3]
        let mono = samples.withUnsafeBufferPointer { Mixdown.interleaved($0, channels: 1) }
        XCTAssertEqual(mono, samples)
    }

    func testInterleavedDropsIncompleteTrailingFrame() {
        let samples: [Float] = [1, 1, 1, 1, 1]
        let mono = samples.withUnsafeBufferPointer { Mixdown.interleaved($0, channels: 2) }
        XCTAssertEqual(mono.count, 2)
    }

    func testInterleavedRejectsInvalidChannelCount() {
        let samples: [Float] = [1, 2]
        XCTAssertTrue(samples.withUnsafeBufferPointer { Mixdown.interleaved($0, channels: 0) }.isEmpty)
        XCTAssertTrue(samples.withUnsafeBufferPointer { Mixdown.interleaved($0, channels: 3) }.isEmpty)
    }

    func testPlanarChannelsAreAveragedToShortest() {
        let left: [Float] = [1, 1, 1, 1]
        let right: [Float] = [0, 0, 0]
        let mono = left.withUnsafeBufferPointer { l in
            right.withUnsafeBufferPointer { r in Mixdown.planar([l, r]) }
        }
        XCTAssertEqual(mono, [0.5, 0.5, 0.5])
    }

    func testPlanarWithoutChannelsIsEmpty() {
        XCTAssertTrue(Mixdown.planar([]).isEmpty)
    }
}
