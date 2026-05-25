import { describe, expect, it } from "vitest";

import {
  knowledgeImportKindLabel,
  knowledgeImportsWirePayload,
} from "@/lib/knowledgeImportMessage";

describe("knowledgeImportKindLabel", () => {
  it("detects PDF from filename", () => {
    expect(knowledgeImportKindLabel("paper.pdf")).toBe("PDF");
  });

  it("detects PDF from mime type", () => {
    expect(knowledgeImportKindLabel("paper.bin", "application/pdf")).toBe("PDF");
  });
});

describe("knowledgeImportsWirePayload", () => {
  it("maps camelCase UI fields to snake_case wire fields", () => {
    expect(
      knowledgeImportsWirePayload([
        {
          filename: "2506.12623v1.pdf",
          path: "knowledge/group_knowledge/uploads/2506-12623v1_cb344e93.pdf",
          title: "2506 12623v1",
          sizeBytes: 17825792,
          mimeType: "application/pdf",
        },
      ]),
    ).toEqual([
      {
        filename: "2506.12623v1.pdf",
        path: "knowledge/group_knowledge/uploads/2506-12623v1_cb344e93.pdf",
        title: "2506 12623v1",
        size_bytes: 17825792,
        mime_type: "application/pdf",
      },
    ]);
  });
});
