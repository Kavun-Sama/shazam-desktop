import XCTest

@testable import HelperCore

final class PCM16Tests: XCTestCase {
    private func int16s(_ data: Data) -> [Int16] {
        stride(from: 0, to: data.count, by: 2).map { offset in
            Int16(bitPattern: UInt16(data[offset]) | UInt16(data[offset + 1]) << 8)
        }
    }

    func testEncodingIsLittleEndian() {
        let data = PCM16.encode([1.0])
        XCTAssertEqual([UInt8](data), [0xFF, 0x7F])
    }

    func testSamplesAreScaledAndClamped() {
        let values = int16s(PCM16.encode([0, 0.5, -1, 2, -2]))
        XCTAssertEqual(values, [0, 16384, -32767, 32767, -32768])
    }

    func testNonFiniteSamplesBecomeSilence() {
        XCTAssertEqual(int16s(PCM16.encode([.nan, .infinity, -.infinity])), [0, 0, 0])
    }

    func testConverterProducesSixteenKilohertzOutput() {
        let converter = MonoPCMConverter(inputRate: 48_000)
        let data = converter.convert([Float](repeating: 0.25, count: 48_000))
        let produced = data.count / 2
        XCTAssertTrue((15_900...16_000).contains(produced), "got \(produced) samples")
    }
}
