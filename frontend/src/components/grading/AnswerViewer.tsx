"use client";

import { useEffect, useState } from "react";
import { Button, SegmentedTabs, Skeleton } from "@/components/ui";
import { review } from "@/lib/endpoints";

/**
 * The original handwritten answer: the region OCR used for the question, or a
 * full page. Images are fetched with the reviewer's token (never public URLs).
 */
export function AnswerViewer({ submissionId, question, pageCount }: { submissionId: string; question: string | null; pageCount: number | null }) {
  const [mode, setMode] = useState<"region" | "page">("region");
  const [page, setPage] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const [img, setImg] = useState<{ url: string; page: number; cropped: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    setLoading(true);
    setError(null);
    review
      .answerImage(submissionId, mode === "region" ? question : null, mode === "page" ? page : null)
      .then((res) => {
        url = res.url;
        if (cancelled) URL.revokeObjectURL(res.url);
        else {
          setImg(res);
          if (mode === "region") setPage(res.page);
        }
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [submissionId, question, mode, page]);

  const pages = pageCount ?? 1;
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        <SegmentedTabs
          label="Answer view"
          value={mode}
          onChange={setMode}
          options={[
            { value: "region", label: question ? `${question} region` : "Answer region" },
            { value: "page", label: "Full page" },
          ]}
        />
        <div className="flex items-center gap-1 text-xs text-fg-muted">
          {mode === "page" && (
            <>
              <Button size="sm" variant="ghost" disabled={page <= 0} onClick={() => setPage((p) => p - 1)} aria-label="Previous page">
                ‹
              </Button>
              <span className="tabular">
                Page {page + 1} / {pages}
              </span>
              <Button size="sm" variant="ghost" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} aria-label="Next page">
                ›
              </Button>
            </>
          )}
          <Button size="sm" variant="ghost" onClick={() => setZoomed((z) => !z)}>
            {zoomed ? "Fit" : "Zoom"}
          </Button>
        </div>
      </div>
      <div className="min-h-[240px] flex-1 overflow-auto bg-surface-sunken p-3">
        {loading && !img && <Skeleton className="h-72 w-full" />}
        {error && <p className="p-6 text-center text-sm text-fg-subtle">Original answer sheet unavailable ({error}).</p>}
        {img && !error && (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated blob URL
          <img
            src={img.url}
            alt={mode === "region" ? `Handwritten answer for ${question ?? "question"}` : `Answer sheet page ${page + 1}`}
            className={zoomed ? "max-w-none" : "mx-auto h-auto max-w-full"}
            style={{ opacity: loading ? 0.5 : 1 }}
          />
        )}
        {img && mode === "region" && !img.cropped && !error && (
          <p className="mt-2 text-center text-[11px] text-fg-subtle">No segmented region recorded — showing the full page.</p>
        )}
      </div>
    </div>
  );
}
