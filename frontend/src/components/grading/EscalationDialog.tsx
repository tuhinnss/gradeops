"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Label, Modal, Select, Textarea } from "@/components/ui";
import { ESCALATION_REASONS, type EscalationReason } from "@/lib/types";

export function EscalationDialog({
  open,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (reason: EscalationReason, notes: string) => void;
}) {
  const [reason, setReason] = useState<EscalationReason | "">("");
  const [notes, setNotes] = useState("");
  useEffect(() => {
    if (open) {
      setReason("");
      setNotes("");
    }
  }, [open]);
  const valid = reason !== "" && (reason !== "other" || notes.trim().length > 0);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Escalate to professor"
      description="The professor will decide the grade. You will not be able to finalise this submission yourself."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" loading={busy} disabled={!valid} onClick={() => reason && onSubmit(reason, notes.trim())}>
            Escalate
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <div>
          <Label htmlFor="esc-reason" hint="(required)">
            Reason
          </Label>
          <Select id="esc-reason" value={reason} onChange={(e) => setReason(e.target.value as EscalationReason)}>
            <option value="" disabled>
              Select a reason…
            </option>
            {ESCALATION_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="esc-notes" hint={reason === "other" ? "(required)" : "(optional)"}>
            Notes for the professor
          </Label>
          <Textarea id="esc-notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} />
        </div>
      </div>
    </Modal>
  );
}
