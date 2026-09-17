// visionocr.swift - 이미지 파일들을 Vision으로 OCR해서 JSON으로 내보냅니다.
// 사용법: visionocr <이미지경로> [<이미지경로> ...]
// 출력: 한 줄에 파일 하나, JSON {"path":..., "w":..., "h":..., "lines":[{"t":텍스트,"x":,"y":,"w":,"h":,"c":신뢰도}]}
// 좌표는 좌상단 원점 픽셀 기준입니다.

import Foundation
import Vision
import CoreGraphics
import ImageIO

func loadCGImage(_ path: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { return nil }
    return img
}

func jsonEscape(_ s: String) -> String {
    var out = ""
    for ch in s.unicodeScalars {
        switch ch {
        case "\"": out += "\\\""
        case "\\": out += "\\\\"
        case "\n": out += "\\n"
        case "\r": out += "\\r"
        case "\t": out += "\\t"
        default:
            if ch.value < 0x20 { out += String(format: "\\u%04x", ch.value) }
            else { out.unicodeScalars.append(ch) }
        }
    }
    return out
}

let args = Array(CommandLine.arguments.dropFirst())
if args.isEmpty {
    FileHandle.standardError.write("사용법: visionocr <이미지> [...]\n".data(using: .utf8)!)
    exit(2)
}

for path in args {
    guard let cg = loadCGImage(path) else {
        FileHandle.standardError.write("이미지 로드 실패: \(path)\n".data(using: .utf8)!)
        continue
    }
    let w = cg.width, h = cg.height
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["ko-KR", "en-US", "ja-JP"]
    req.revision = VNRecognizeTextRequestRevision3

    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) }
    catch {
        FileHandle.standardError.write("인식 실패 \(path): \(error)\n".data(using: .utf8)!)
        continue
    }

    var parts: [String] = []
    for obs in (req.results ?? []) {
        guard let cand = obs.topCandidates(1).first else { continue }
        let bb = obs.boundingBox   // 정규화, 좌하단 원점
        let px = bb.origin.x * Double(w)
        let py = (1.0 - bb.origin.y - bb.height) * Double(h)   // 좌상단 원점으로 뒤집기
        let pw = bb.width * Double(w)
        let ph = bb.height * Double(h)
        parts.append("{\"t\":\"\(jsonEscape(cand.string))\",\"x\":\(px),\"y\":\(py),\"w\":\(pw),\"h\":\(ph),\"c\":\(cand.confidence)}")
    }
    print("{\"path\":\"\(jsonEscape(path))\",\"w\":\(w),\"h\":\(h),\"lines\":[\(parts.joined(separator: ","))]}")
}
