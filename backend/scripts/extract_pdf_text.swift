import Foundation
import PDFKit

if CommandLine.arguments.count < 2 {
    fputs("usage: swift extract_pdf_text.swift <pdf-path>\n", stderr)
    exit(1)
}

let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)

guard let document = PDFDocument(url: url) else {
    fputs("failed to open PDF\n", stderr)
    exit(2)
}

for pageIndex in 0..<document.pageCount {
    if let page = document.page(at: pageIndex), let text = page.string {
        print("<<<PAGE:\(pageIndex + 1)>>>")
        print(text)
    }
}

