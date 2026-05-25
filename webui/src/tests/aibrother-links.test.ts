import { describe, expect, it } from "vitest";

import {
  joinKnowledgeAssetPath,
  rewriteKnowledgeMarkdownAssets,
} from "@/lib/aibrother-links";

describe("aibrother asset links", () => {
  it("joins relative asset paths against the markdown document directory", () => {
    expect(
      joinKnowledgeAssetPath(
        "knowledge/group_knowledge/uploads/image_10505b0e.md",
        "assets/10505b0e_image.png",
      ),
    ).toBe("knowledge/group_knowledge/uploads/assets/10505b0e_image.png");
  });

  it("rewrites relative markdown images to authenticated asset URLs", () => {
    const content = "![image.png](assets/10505b0e_image.png)";
    const rewritten = rewriteKnowledgeMarkdownAssets(
      content,
      "knowledge/group_knowledge/uploads/image_10505b0e.md",
      "tok-123",
    );
    expect(rewritten).toContain("/api/aibrother/asset?");
    expect(rewritten).toContain(
      "path=knowledge%2Fgroup_knowledge%2Fuploads%2Fassets%2F10505b0e_image.png",
    );
    expect(rewritten).toContain("token=tok-123");
  });
});
