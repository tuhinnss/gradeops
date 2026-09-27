"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Label, Modal, Textarea } from "@/components/ui";

export function ReturnDialog({ open, busy, error, onClose, onSubmit }: { open: boolean; busy?: boolean; error?: string | null; onClose: () => void; onSubmit: (notes: string) => void }) {
  const [notes, setNotes] = useState("");
  useEffect(() => {
    if (open) setNotes("");
  }, [open]);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Return to TA"
      description="The submission goes back into the TA review queue with your instructions."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" loading={busy} disabled={!notes.trim()} onClick={() => onSubmit(notes.trim())}>
            Return to TA
          </Button>
        </>
      }
    >
      {error && <Alert tone="error" className="mb-3">{error}</Alert>}
      <Label htmlFor="return-notes" hint="(required)">
        What should the TA re-check?
      </Label>
      <Textarea id="return-notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} />
    </Modal>
  );
}
