import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Modal,
  Pressable,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../src/utils/colors';
import { fmtAmount, confTier, SUPPLIER_FIELD_NAMES, FIELD_ORDER, fieldLabel } from '../src/utils/formatters';
import { hapticSuccess, hapticError } from '../src/utils/haptics';
import { saveInvoice } from '../src/services/invoiceService';
import { calculateRate } from '../src/services/calculations';
import SectionCard from '../src/components/SectionCard';
import FieldRow from '../src/components/FieldRow';
import LineItemCard from '../src/components/LineItemCard';
import StatusBadge from '../src/components/StatusBadge';
import type { ExtractionResult, ExtractedField, ExtractedLineItem, LineItem } from '../src/types';

// ─── Helpers ──────────────────────────────────────────────────

function extractSupplierFields(fields: ExtractedField[]) {
  return fields.filter((f) => SUPPLIER_FIELD_NAMES.has(f.field_name));
}

// Fields to hide from Invoice Details
const EXCLUDED_FIELDS = new Set(['vat', 'vat_amount', 'document_type']);

function getNonSupplierFields(fields: ExtractedField[]) {
  return fields.filter(
    (f) =>
      !SUPPLIER_FIELD_NAMES.has(f.field_name) &&
      !EXCLUDED_FIELDS.has(f.field_name) &&
      !f.field_name.toLowerCase().includes('vat')
  );
}

function sortFields(fields: ExtractedField[]) {
  const orderMap: Record<string, number> = {};
  FIELD_ORDER.forEach((name, i) => {
    orderMap[name] = i;
  });
  return [...fields].sort((a, b) => {
    const ai = orderMap[a.field_name] ?? 999;
    const bi = orderMap[b.field_name] ?? 999;
    return ai - bi;
  });
}

function buildTaxInfo(fields: ExtractedField[], lineItems: ExtractedLineItem[]) {
  const fieldMap: Record<string, string> = {};
  const confMap: Record<string, number> = {};
  for (const f of fields) {
    fieldMap[f.field_name] = f.value;
    confMap[f.field_name] = f.confidence;
  }

  const taxRaw = fieldMap.total_tax_amount ?? fieldMap.tax_amount ?? fieldMap.gst_amount;
  const taxConf = confMap.total_tax_amount ?? confMap.tax_amount ?? confMap.gst_amount;
  if (taxRaw == null) return null;

  const taxAmount = parseFloat(String(taxRaw).replace(/,/g, ''));

  // 3-step subtotal fallback
  let subtotal = NaN;
  let subtotalSource: string | null = null;

  const subtotalRaw = fieldMap.net_amount ?? fieldMap.subtotal;
  if (subtotalRaw) {
    subtotal = parseFloat(String(subtotalRaw).replace(/,/g, ''));
    subtotalSource = 'field';
  }

  if (isNaN(subtotal) && lineItems.length > 0) {
    const sum = lineItems.reduce((acc, li) => {
      const amt = parseFloat(String(li.amount));
      return acc + (isNaN(amt) ? 0 : amt);
    }, 0);
    if (sum > 0) {
      subtotal = sum;
      subtotalSource = 'line_items';
    }
  }

  if (isNaN(subtotal) && fieldMap.total_amount && !isNaN(taxAmount)) {
    const total = parseFloat(String(fieldMap.total_amount).replace(/,/g, ''));
    if (!isNaN(total)) {
      subtotal = total - taxAmount;
      subtotalSource = 'derived';
    }
  }

  const taxPct =
    !isNaN(taxAmount) && !isNaN(subtotal) && subtotal !== 0
      ? (taxAmount / subtotal) * 100
      : null;

  return {
    taxAmount,
    taxConf,
    taxPct,
    subtotal,
    subtotalSource,
    totalAmount: fieldMap.total_amount
      ? parseFloat(String(fieldMap.total_amount).replace(/,/g, ''))
      : null,
    totalConf: confMap.total_amount,
  };
}

// ─── Screen ───────────────────────────────────────────────────

export default function ExtractionResultsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();

  // Parse the extraction result from route params
  const extractionResult: ExtractionResult | null = useMemo(() => {
    try {
      const raw = params.data || params.result;
      if (raw) return JSON.parse(raw as string);
    } catch {}
    return null;
  }, [params.data, params.result]);

  const fileName = (params.fileName as string) || extractionResult?.original_filename || 'Invoice';

  const [lineItems, setLineItems] = useState<ExtractedLineItem[]>(
    extractionResult?.line_items ?? []
  );
  const [saving, setSaving] = useState(false);
  const [warningsVisible, setWarningsVisible] = useState(false);

  if (!extractionResult) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>No extraction data found.</Text>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
          <Text style={styles.backBtnText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const supplierFields = extractSupplierFields(extractionResult.fields);
  const invoiceFields = sortFields(getNonSupplierFields(extractionResult.fields));
  const taxInfo = buildTaxInfo(extractionResult.fields, lineItems);

  // ─── Line item editing ──────────────────────────────────

  const handleLineItemChange = (
    index: number,
    field: string,
    value: string | number | null
  ) => {
    setLineItems((prev) => {
      const updated = [...prev];
      const item = { ...updated[index], [field]: value } as any;

      // Auto-calc rate when qty or amount changes
      if (field === 'quantity' || field === 'amount') {
        const qty = parseFloat(String(item.quantity));
        const amount = parseFloat(String(item.amount));
        if (!isNaN(qty) && !isNaN(amount) && qty !== 0) {
          item.unit_price = calculateRate(amount, qty);
        }
      }

      updated[index] = item;
      return updated;
    });
  };

  // ─── Save ───────────────────────────────────────────────

  const handleSave = async (status: 'draft' | 'pending_processing') => {
    setSaving(true);
    try {
      const fieldMap: Record<string, string> = {};
      for (const f of extractionResult.fields) {
        fieldMap[f.field_name] = f.value;
      }

      const confMap: Record<string, number> = {};
      for (const f of extractionResult.fields) {
        confMap[f.field_name] = f.confidence;
      }

      const payload = {
        original_filename: extractionResult.original_filename,
        stored_filepath: extractionResult.stored_filepath,
        page_count: extractionResult.page_count,
        processing_time_ms: extractionResult.processing_time_ms,
        overall_confidence: extractionResult.overall_confidence,
        document_type: extractionResult.document_type,
        warnings: extractionResult.warnings,
        invoice_number: fieldMap.invoice_number ?? fieldMap.invoice_id ?? null,
        invoice_date: fieldMap.invoice_date ?? null,
        due_date: fieldMap.due_date ?? null,
        currency: fieldMap.currency ?? 'PKR',
        supplier_name: fieldMap.supplier_name ?? null,
        supplier_address: fieldMap.supplier_address ?? null,
        supplier_ntn: fieldMap.supplier_tax_id ?? null,
        receiver_name: fieldMap.receiver_name ?? null,
        receiver_address: fieldMap.receiver_address ?? null,
        subtotal_amount: fieldMap.net_amount
          ? parseFloat(String(fieldMap.net_amount).replace(/,/g, ''))
          : null,
        tax_amount: fieldMap.total_tax_amount
          ? parseFloat(String(fieldMap.total_tax_amount).replace(/,/g, ''))
          : null,
        total_amount: fieldMap.total_amount
          ? parseFloat(String(fieldMap.total_amount).replace(/,/g, ''))
          : null,
        po_reference: fieldMap.purchase_order ?? null,
        field_confidences: confMap,
        status,
        source_type: 'mobile_upload',
        line_items: lineItems.map((li) => ({
          description: li.description ?? 'N/A',
          quantity: li.quantity ?? 1,
          unit: li.unit ?? '',
          unit_price: li.unit_price ?? 0,
          amount: li.amount ?? 0,
        })),
      };

      await saveInvoice(payload);
      hapticSuccess();
      Alert.alert('Saved', `Invoice saved as ${status === 'draft' ? 'Draft' : 'Pending'}.`, [
        {
          text: 'OK',
          onPress: () => {
            router.replace('/(tabs)/invoices');
          },
        },
      ]);
    } catch (err: any) {
      hapticError();
      Alert.alert('Save Error', err?.message || 'Failed to save invoice.');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    Alert.alert('Discard', 'Discard extraction results and go back?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: () => router.back() },
    ]);
  };

  // ─── KPI values ─────────────────────────────────────────

  const confidence = extractionResult.overall_confidence;
  const confLevel = confTier(confidence);

  return (
    <View style={styles.flex}>
      <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
        {/* File Info Bar */}
        <View style={styles.fileBar}>
          <View style={styles.fileInfo}>
            <Ionicons name="document-text" size={20} color={colors.brand[500]} />
            <View style={{ marginLeft: 8, flex: 1 }}>
              <Text style={styles.fileName} numberOfLines={1}>
                {fileName}
              </Text>
              <Text style={styles.fileMeta}>
                {extractionResult.page_count
                  ? `${extractionResult.page_count} page${extractionResult.page_count !== 1 ? 's' : ''}`
                  : ''}
                {extractionResult.processing_time_ms
                  ? ` · ${(extractionResult.processing_time_ms / 1000).toFixed(1)}s`
                  : ''}
              </Text>
            </View>
          </View>
          <View style={styles.fileBarRight}>
            {extractionResult.warnings?.length > 0 && (
              <TouchableOpacity
                style={styles.warningIconBtn}
                onPress={() => setWarningsVisible(true)}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons name="warning" size={18} color={colors.warning[600]} />
                <View style={styles.warningBadge}>
                  <Text style={styles.warningBadgeText}>
                    {extractionResult.warnings.length}
                  </Text>
                </View>
              </TouchableOpacity>
            )}
            <StatusBadge status="validated" label="Extracted" />
          </View>
        </View>

        {/* Warnings Modal */}
        {extractionResult.warnings?.length > 0 && (
          <Modal
            visible={warningsVisible}
            transparent
            animationType="fade"
            onRequestClose={() => setWarningsVisible(false)}
          >
            <Pressable style={styles.modalOverlay} onPress={() => setWarningsVisible(false)}>
              <Pressable style={styles.modalContent} onPress={() => {}}>
                <View style={styles.modalHeader}>
                  <View style={styles.modalTitleRow}>
                    <Ionicons name="warning" size={20} color={colors.warning[600]} />
                    <Text style={styles.modalTitle}>
                      {extractionResult.warnings.length} Warning{extractionResult.warnings.length !== 1 ? 's' : ''}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => setWarningsVisible(false)}>
                    <Ionicons name="close" size={22} color={colors.neutral[500]} />
                  </TouchableOpacity>
                </View>
                <ScrollView style={styles.modalBody}>
                  {extractionResult.warnings.map((w, i) => (
                    <View key={i} style={styles.modalWarningRow}>
                      <View style={styles.modalBullet} />
                      <Text style={styles.modalWarningText}>{w}</Text>
                    </View>
                  ))}
                </ScrollView>
              </Pressable>
            </Pressable>
          </Modal>
        )}

        {/* KPI Bar */}
        <View style={styles.kpiBar}>
          <View style={styles.kpiItem}>
            <Text style={styles.kpiLabel}>Confidence</Text>
            <Text
              style={[
                styles.kpiValue,
                {
                  color:
                    confLevel === 'high'
                      ? colors.success[600]
                      : confLevel === 'medium'
                      ? colors.warning[600]
                      : colors.danger[600],
                },
              ]}
            >
              {confidence != null ? `${confidence}%` : '—'}
            </Text>
          </View>
          <View style={styles.kpiDivider} />
          <View style={styles.kpiItem}>
            <Text style={styles.kpiLabel}>Line Items</Text>
            <Text style={styles.kpiValue}>{lineItems.length}</Text>
          </View>
          <View style={styles.kpiDivider} />
          <View style={styles.kpiItem}>
            <Text style={styles.kpiLabel}>Fields</Text>
            <Text style={styles.kpiValue}>{extractionResult.fields.length}</Text>
          </View>
        </View>

        {/* Supplier Info */}
        {supplierFields.length > 0 && (
          <SectionCard title="Supplier Information" defaultOpen>
            {supplierFields.map((f) => (
              <FieldRow
                key={f.field_name}
                label={fieldLabel(f.field_name)}
                value={f.value}
                confidence={f.confidence}
              />
            ))}
            {/* Status indicators */}
            <View style={styles.statusRow}>
              <View style={styles.statusColumn}>
                <Text style={styles.statusLabel}>Tax Payer Status</Text>
                <View style={[styles.statusPill, styles.statusPillActive]}>
                  <View style={[styles.statusDot, styles.dotActive]} />
                  <Text style={[styles.statusPillText, styles.statusTextActive]}>Active</Text>
                </View>
              </View>
              <View style={styles.statusColumn}>
                <Text style={styles.statusLabel}>ERP Registration</Text>
                <View style={[styles.statusPill, styles.statusPillAmber]}>
                  <View style={[styles.statusDot, styles.dotAmber]} />
                  <Text style={[styles.statusPillText, styles.statusTextAmber]}>Not Registered</Text>
                </View>
              </View>
            </View>
          </SectionCard>
        )}

        {/* Invoice Details */}
        {invoiceFields.length > 0 && (
          <SectionCard title="Invoice Details" defaultOpen>
            {invoiceFields.map((f) => (
              <FieldRow
                key={f.field_name}
                label={f.label || fieldLabel(f.field_name)}
                value={f.value}
                confidence={f.confidence}
              />
            ))}
          </SectionCard>
        )}

        {/* Line Items */}
        <SectionCard title={`Line Items (${lineItems.length})`} defaultOpen>
          {lineItems.length === 0 ? (
            <Text style={styles.emptyText}>No line items extracted.</Text>
          ) : (
            lineItems.map((li, idx) => (
              <LineItemCard
                key={idx}
                index={idx}
                item={{
                  description: li.description,
                  quantity: li.quantity,
                  unit: li.unit,
                  unit_price: li.unit_price,
                  amount: li.amount,
                }}
                onChange={handleLineItemChange}
              />
            ))
          )}
        </SectionCard>

        {/* Sales Tax */}
        <SectionCard title="Sales Tax" defaultOpen>
          {taxInfo ? (
            <>
              <FieldRow
                label="Sales Tax Amount"
                value={!isNaN(taxInfo.taxAmount) ? fmtAmount(taxInfo.taxAmount) : fmtAmount(0)}
                confidence={taxInfo.taxConf}
              />
              <FieldRow
                label="Sales Tax %"
                value={taxInfo.taxPct != null ? `${taxInfo.taxPct.toFixed(2)}%` : '0%'}
              />
              {!isNaN(taxInfo.subtotal) && (
                <FieldRow
                  label={`Subtotal${
                    taxInfo.subtotalSource === 'line_items'
                      ? ' (from line items)'
                      : taxInfo.subtotalSource === 'derived'
                      ? ' (derived)'
                      : ''
                  }`}
                  value={fmtAmount(taxInfo.subtotal)}
                />
              )}
              {taxInfo.totalAmount != null && !isNaN(taxInfo.totalAmount) && (
                <FieldRow
                  label="Total Amount"
                  value={fmtAmount(taxInfo.totalAmount)}
                  confidence={taxInfo.totalConf}
                />
              )}
            </>
          ) : (
            <>
              <FieldRow label="Sales Tax Amount" value={fmtAmount(0)} />
              <FieldRow label="Sales Tax %" value="0%" />
            </>
          )}
        </SectionCard>

        {/* Spacer for bottom bar */}
        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Bottom Action Bar */}
      <View style={styles.bottomBar}>
        <TouchableOpacity style={styles.discardBtn} onPress={handleDiscard} disabled={saving}>
          <Text style={styles.discardBtnText}>Discard</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.draftBtn}
          onPress={() => handleSave('draft')}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator size="small" color={colors.brand[600]} />
          ) : (
            <Text style={styles.draftBtnText}>Save Draft</Text>
          )}
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.submitBtn}
          onPress={() => handleSave('pending_processing')}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={16} color="#fff" />
              <Text style={styles.submitBtnText}>Submit</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: {
    flex: 1,
    backgroundColor: colors.neutral[50],
  },
  scrollContent: {
    padding: 16,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  errorText: {
    fontSize: 15,
    color: colors.neutral[500],
    marginBottom: 16,
  },
  backBtn: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: colors.brand[600],
    borderRadius: 8,
  },
  backBtnText: {
    color: '#fff',
    fontWeight: '600',
  },

  // File bar
  fileBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginBottom: 12,
  },
  fileInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 12,
  },
  fileName: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.neutral[800],
  },
  fileMeta: {
    fontSize: 11,
    color: colors.neutral[400],
    marginTop: 2,
  },

  // KPI bar
  kpiBar: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginBottom: 12,
    alignItems: 'center',
  },
  kpiItem: {
    flex: 1,
    alignItems: 'center',
  },
  kpiLabel: {
    fontSize: 10,
    color: colors.neutral[400],
    textTransform: 'uppercase',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  kpiValue: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.neutral[800],
  },
  kpiDivider: {
    width: 1,
    height: 28,
    backgroundColor: colors.neutral[200],
  },

  // File bar right side
  fileBarRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  warningIconBtn: {
    position: 'relative',
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: colors.warning[50],
    alignItems: 'center',
    justifyContent: 'center',
  },
  warningBadge: {
    position: 'absolute',
    top: -4,
    right: -4,
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: colors.warning[600],
    alignItems: 'center',
    justifyContent: 'center',
  },
  warningBadgeText: {
    fontSize: 9,
    fontWeight: '700',
    color: '#fff',
  },

  // Warning modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 16,
    maxHeight: '60%',
    overflow: 'hidden',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 18,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  modalTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.neutral[800],
  },
  modalBody: {
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  modalWarningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
    gap: 10,
  },
  modalBullet: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.warning[500],
    marginTop: 6,
  },
  modalWarningText: {
    flex: 1,
    fontSize: 14,
    color: colors.neutral[700],
    lineHeight: 20,
  },

  // Status pills (Tax Payer / ERP)
  statusRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.neutral[100],
  },
  statusColumn: {
    flex: 1,
  },
  statusLabel: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.neutral[500],
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 20,
    borderWidth: 1,
  },
  statusPillActive: {
    backgroundColor: '#ecfdf5',
    borderColor: '#a7f3d0',
  },
  statusPillAmber: {
    backgroundColor: '#fffbeb',
    borderColor: '#fde68a',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  dotActive: {
    backgroundColor: '#10b981',
  },
  dotAmber: {
    backgroundColor: '#f59e0b',
  },
  statusPillText: {
    fontSize: 11,
    fontWeight: '600',
  },
  statusTextActive: {
    color: '#047857',
  },
  statusTextAmber: {
    color: '#b45309',
  },

  emptyText: {
    fontSize: 13,
    color: colors.neutral[400],
    textAlign: 'center',
    paddingVertical: 16,
  },

  // Bottom bar
  bottomBar: {
    flexDirection: 'row',
    padding: 16,
    paddingBottom: 32,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: colors.neutral[200],
    gap: 10,
  },
  discardBtn: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.neutral[300],
    borderRadius: 10,
  },
  discardBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.neutral[500],
  },
  draftBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.brand[300],
    borderRadius: 10,
  },
  draftBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.brand[600],
  },
  submitBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    backgroundColor: colors.brand[600],
    borderRadius: 10,
  },
  submitBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#fff',
  },
});
