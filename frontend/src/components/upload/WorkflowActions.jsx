import Card from "../common/Card";
import Button from "../common/Button";

export default function WorkflowActions({ onDiscard, onSaveDraft, onSubmit, saving = false }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-neutral-800 mb-0.5">
            Ready to submit for processing
          </div>
          <div className="text-2xs text-neutral-500">
            Invoice will go through validation, 3-way matching, and tax determination
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onDiscard} disabled={saving}>
            Discard
          </Button>
          <Button variant="secondary" size="sm" onClick={onSaveDraft} disabled={saving}>
            {saving ? "Saving..." : "Save as Draft"}
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={saving}>
            Submit for Processing &rarr;
          </Button>
        </div>
      </div>
    </Card>
  );
}
