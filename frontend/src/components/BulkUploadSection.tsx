"use client";

import { useCallback, useRef, useState } from "react";
import {
  bulkUploadPdfs,
  bulkUploadZip,
  createBatchJob,
  getBatchJob,
  type BulkUploadItem,
} from "@/lib/api";

type Props = {
  rubricId: string | null;
  onUploaded: (items: BulkUploadItem[]) => void;
  onBanner: (msg: string) => void;
};

export function BulkUploadSection({ rubricId, onUploaded, onBanner }: Props) {
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [jobProgress, setJobProgress] = useState<number | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      const pdfs = list.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
      const zips = list.filter((f) => f.name.toLowerCase().endsWith(".zip"));

      if (pdfs.length === 0 && zips.length === 0) {
        onBanner("Drop PDF files or a ZIP archive.");
        return;
      }

      setBusy(true);
      setJobProgress(null);
      setJobStatus(null);

      try {
        let uploaded: BulkUploadItem[] = [];

        if (pdfs.length > 0) {
          const res = await bulkUploadPdfs(pdfs, rubricId);
          uploaded = [...uploaded, ...res.uploaded];
          if (res.failed.length) {
            onBanner(`${res.message} (${res.failed.length} failed)`);
          }
        }

        for (const zip of zips) {
          const res = await bulkUploadZip(zip, rubricId);
          uploaded = [...uploaded, ...res.uploaded];
        }

        if (uploaded.length > 0) {
          onUploaded(uploaded);
          onBanner(`Bulk upload: ${uploaded.length} sheet(s) added.`);

          if (rubricId) {
            const job = await createBatchJob(
              rubricId,
              uploaded.map((u) => u.id),
              true
            );
            setJobStatus(job.status);
            setJobProgress(job.progress_percent);

            const poll = async () => {
              const j = await getBatchJob(job.id);
              setJobProgress(j.progress_percent);
              setJobStatus(j.status);
              if (j.status === "running" || j.status === "queued") {
                setTimeout(poll, 2000);
              } else {
                onBanner(
                  `Batch evaluation ${j.status}: ${j.completed_count}/${j.total_count} done.`
                );
              }
            };
            setTimeout(poll, 1500);
          }
        }
      } catch (err) {
        onBanner(err instanceof Error ? err.message : "Bulk upload failed");
      } finally {
        setBusy(false);
      }
    },
    [rubricId, onUploaded, onBanner]
  );

  return (
    <section className="rounded-2xl border border-dashed border-sky-500/30 bg-sky-950/20 p-6">
      <h2 className="text-lg font-semibold text-white">Bulk upload</h2>
      <p className="mt-1 text-sm text-zinc-500">
        Drop multiple PDFs or a ZIP. Student IDs are inferred from filenames. Starts batch
        evaluation when a rubric is loaded.
      </p>

      <div
        className={`mt-4 cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition ${
          dragOver
            ? "border-sky-400 bg-sky-950/40"
            : "border-white/15 bg-black/30 hover:border-white/25"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.zip,application/pdf,application/zip"
          className="hidden"
          disabled={busy}
          onChange={(e) => {
            if (e.target.files?.length) void handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <p className="text-sm text-zinc-400">
          {busy ? "Uploading…" : "Drag & drop PDFs or ZIP here, or click to browse"}
        </p>
      </div>

      {jobProgress != null && (
        <div className="mt-4">
          <div className="flex justify-between text-xs text-zinc-500">
            <span>Batch job: {jobStatus}</span>
            <span>{jobProgress.toFixed(0)}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/50">
            <div
              className="h-full bg-sky-500 transition-all"
              style={{ width: `${jobProgress}%` }}
            />
          </div>
        </div>
      )}
    </section>
  );
}
