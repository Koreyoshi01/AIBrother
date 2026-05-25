import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MarkdownTextRenderer from "@/components/MarkdownTextRenderer";
import {
  AIBROTHER_OPEN_FILE_EVENT,
  type AIBrotherOpenFileDetail,
} from "@/lib/aibrother-links";

describe("MarkdownTextRenderer", () => {
  it("renders markdown images as inline previews", () => {
    render(<MarkdownTextRenderer>![Diagram](/api/media/sig/payload)</MarkdownTextRenderer>);

    const image = screen.getByRole("img", { name: "Diagram" });
    expect(image).toHaveAttribute("src", "/api/media/sig/payload");
    expect(screen.getByRole("link", { name: "Open Diagram" })).toHaveAttribute(
      "href",
      "/api/media/sig/payload",
    );
    expect(screen.getByText("Diagram")).toBeInTheDocument();
  });

  it("dispatches app navigation for AI Brother knowledge links", () => {
    const listener = vi.fn((event: Event) => {
      const detail = (event as CustomEvent<AIBrotherOpenFileDetail>).detail;
      expect(detail.path).toBe("co2_absorption.md");
    });
    window.addEventListener(AIBROTHER_OPEN_FILE_EVENT, listener);
    try {
      render(<MarkdownTextRenderer>[co2_absorption.md](co2_absorption.md)</MarkdownTextRenderer>);

      fireEvent.click(screen.getByRole("link", { name: "co2_absorption.md" }));

      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(AIBROTHER_OPEN_FILE_EVENT, listener);
    }
  });

  it("dispatches app navigation for inline AI Brother file chips", () => {
    const listener = vi.fn((event: Event) => {
      const detail = (event as CustomEvent<AIBrotherOpenFileDetail>).detail;
      expect(detail.path).toBe("knowledge/lab_manual/co2_absorption.md");
    });
    window.addEventListener(AIBROTHER_OPEN_FILE_EVENT, listener);
    try {
      render(
        <MarkdownTextRenderer>
          {"`knowledge/lab_manual/co2_absorption.md`"}
        </MarkdownTextRenderer>,
      );

      fireEvent.click(screen.getByTestId("inline-file-path"));

      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(AIBROTHER_OPEN_FILE_EVENT, listener);
    }
  });
});
