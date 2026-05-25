import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadComposer } from "@/components/thread/ThreadComposer";
import type { EncodeResponse } from "@/lib/imageEncode";
import type { KnowledgeImportFn } from "@/hooks/useAttachedImages";

const encodeImage = vi.fn<(file: File) => Promise<EncodeResponse>>();

vi.mock("@/lib/imageEncode", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/imageEncode")>();
  return {
    ...actual,
    encodeImage: (file: File) => encodeImage(file),
  };
});

function renderComposer(onSend = vi.fn()) {
  const importToKnowledge = vi.fn<KnowledgeImportFn>().mockResolvedValue({
    path: "knowledge/group_knowledge/uploads/test.md",
    title: "test",
    category: "group_knowledge",
    category_label: "组内经验",
    preview: "preview",
  });
  render(
    <ThreadComposer onSend={onSend} importToKnowledge={importToKnowledge} />,
  );
  return { importToKnowledge };
}

function pngFile(name = "a.png", size = 10) {
  return new File([new Uint8Array(size)], name, { type: "image/png" });
}

function resolveReady(file: File): EncodeResponse {
  return {
    id: "stub",
    ok: true,
    dataUrl: `data:image/png;base64,${btoa(file.name)}`,
    mime: "image/png",
    bytes: file.size,
    origBytes: file.size,
    normalized: false,
  };
}

beforeEach(() => {
  encodeImage.mockReset();
  let id = 0;
  if (!(globalThis.URL as unknown as { createObjectURL?: unknown }).createObjectURL) {
    (globalThis.URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL =
      () => `blob:mock/${++id}`;
  }
  if (!(globalThis.URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL) {
    (globalThis.URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL =
      () => {};
  }
});

describe("ThreadComposer — image attachments", () => {
  it("imports a picked PDF into the knowledge base and sends text only", async () => {
    const file = new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" });
    const onSend = vi.fn();

    const { importToKnowledge } = renderComposer(onSend);

    const input = screen
      .getByLabelText(/message input/i)
      .closest("form")!
      .querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    await waitFor(() =>
      expect(screen.getByTestId("composer-chip")).toBeInTheDocument(),
    );

    await waitFor(() => {
      expect(importToKnowledge).toHaveBeenCalledWith(
        expect.stringContaining("data:application/pdf;base64,"),
        file,
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/已入库|In knowledge base/i)).toBeInTheDocument();
    });

    const textarea = screen.getByLabelText(/message input/i);
    fireEvent.change(textarea, { target: { value: "请总结这份 PDF" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(onSend).toHaveBeenCalledTimes(1);
    const [content, attachments] = onSend.mock.calls[0];
    expect(content).toBe("请总结这份 PDF");
    expect(attachments).toBeUndefined();
  });

  it("imports a picked TXT file into the knowledge base", async () => {
    const file = new File(["课题组实验记录"], "notes.txt", { type: "text/plain" });
    const onSend = vi.fn();
    const { importToKnowledge } = renderComposer(onSend);

    const input = screen
      .getByLabelText(/message input/i)
      .closest("form")!
      .querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    await waitFor(() =>
      expect(screen.getByTestId("composer-chip")).toBeInTheDocument(),
    );

    await waitFor(() => {
      expect(importToKnowledge).toHaveBeenCalledWith(
        expect.stringContaining("data:text/plain;base64,"),
        file,
      );
    });
  });

  it("imports a picked image into the knowledge base and sends text only", async () => {
    const file = pngFile("a.png");
    encodeImage.mockResolvedValueOnce(resolveReady(file));
    const onSend = vi.fn();

    const { importToKnowledge } = renderComposer(onSend);

    const input = screen
      .getByLabelText(/message input/i)
      .closest("form")!
      .querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    await waitFor(() =>
      expect(screen.getByTestId("composer-chip")).toBeInTheDocument(),
    );

    await waitFor(() => {
      expect(importToKnowledge).toHaveBeenCalled();
    });

    const textarea = screen.getByLabelText(/message input/i);
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(onSend).toHaveBeenCalledTimes(1);
    const [content, images] = onSend.mock.calls[0];
    expect(content).toBe("hi");
    expect(images).toBeUndefined();
  });

  it("blocks send while an attachment is still encoding", async () => {
    const file = pngFile("slow.png");
    let resolveEncode: (r: EncodeResponse) => void = () => {};
    encodeImage.mockReturnValueOnce(
      new Promise((r) => {
        resolveEncode = r;
      }),
    );
    const onSend = vi.fn();

    const { importToKnowledge } = renderComposer(onSend);

    const fileInput = screen
      .getByLabelText(/message input/i)
      .closest("form")!
      .querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } });
    });

    const textarea = screen.getByLabelText(/message input/i);
    fireEvent.change(textarea, { target: { value: "hello" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();

    await act(async () => {
      resolveEncode(resolveReady(file));
      await Promise.resolve();
    });

    await waitFor(() => expect(importToKnowledge).toHaveBeenCalled());

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("rejects a non-image paste silently without adding a chip", async () => {
    const onSend = vi.fn();
    renderComposer(onSend);
    const textarea = screen.getByLabelText(/message input/i);

    fireEvent.paste(textarea, {
      clipboardData: {
        files: [],
        items: [
          {
            kind: "string",
            type: "text/plain",
            getAsFile: () => null,
          },
        ],
        types: ["text/plain"],
        getData: () => "some pasted text",
      },
    });

    expect(screen.queryByTestId("composer-chip")).toBeNull();
    expect(encodeImage).not.toHaveBeenCalled();
  });

  it("surfaces an inline error when encoding fails", async () => {
    const file = pngFile("bad.png");
    encodeImage.mockResolvedValueOnce({
      id: "stub",
      ok: false,
      reason: "decode_failed",
    } as EncodeResponse);
    const onSend = vi.fn();

    const { importToKnowledge } = renderComposer(onSend);
    const fileInput = screen
      .getByLabelText(/message input/i)
      .closest("form")!
      .querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } });
    });

    await waitFor(() => {
      const chip = screen.getByTestId("composer-chip");
      expect(chip.textContent ?? "").toMatch(/decode|image/i);
    });

    const textarea = screen.getByLabelText(/message input/i);
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });
});
