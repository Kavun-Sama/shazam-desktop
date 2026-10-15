import XCTest

@testable import HelperCore

final class StreamResamplerTests: XCTestCase {
    private func sine(_ frequency: Double, rate: Double, count: Int) -> [Float] {
        (0..<count).map { Float(sin(2 * Double.pi * frequency * Double($0) / rate)) }
    }

    private func rms(_ samples: ArraySlice<Float>) -> Double {
        let sum = samples.reduce(0.0) { $0 + Double($1) * Double($1) }
        return (sum / Double(samples.count)).squareRoot()
    }

    func testEqualRatesPassThrough() {
        let resampler = StreamResampler(inputRate: 16_000, outputRate: 16_000)
        XCTAssertEqual(resampler.process([0.1, 0.2, 0.3]), [0.1, 0.2, 0.3])
    }

    func testDownsampledLengthMatchesRatio() {
        let resampler = StreamResampler(inputRate: 48_000, outputRate: 16_000)
        let output = resampler.process(sine(440, rate: 48_000, count: 48_000))
        XCTAssertTrue((15_900...16_000).contains(output.count), "got \(output.count)")
    }

    func testPassbandToneKeepsItsAmplitude() {
        let resampler = StreamResampler(inputRate: 48_000, outputRate: 16_000)
        let output = resampler.process(sine(1_000, rate: 48_000, count: 48_000))
        let level = rms(output[1_000..<14_000])
        XCTAssertEqual(level, 0.5.squareRoot(), accuracy: 0.02)
    }

    func testToneAboveTheNewNyquistIsRejected() {
        let resampler = StreamResampler(inputRate: 48_000, outputRate: 16_000)
        let output = resampler.process(sine(12_000, rate: 48_000, count: 48_000))
        XCTAssertLessThan(rms(output[1_000..<14_000]), 0.01)
    }

    func testChunkedProcessingMatchesSingleShot() {
        let input = sine(700, rate: 44_100, count: 22_050)
        let whole = StreamResampler(inputRate: 44_100, outputRate: 16_000).process(input)

        let chunked = StreamResampler(inputRate: 44_100, outputRate: 16_000)
        var pieces: [Float] = []
        var offset = 0
        for size in [1, 7, 480, 1_024, 333, 4_096] where offset < input.count {
            let end = min(input.count, offset + size)
            pieces += chunked.process(Array(input[offset..<end]))
            offset = end
        }
        pieces += chunked.process(Array(input[offset...]))

        XCTAssertEqual(pieces.count, whole.count)
        for (a, b) in zip(pieces, whole) { XCTAssertEqual(a, b, accuracy: 1e-5) }
    }

    func testUpsamplingIsSupported() {
        let resampler = StreamResampler(inputRate: 8_000, outputRate: 16_000)
        let output = resampler.process(sine(500, rate: 8_000, count: 8_000))
        XCTAssertTrue((15_900...16_000).contains(output.count), "got \(output.count)")
    }
}
