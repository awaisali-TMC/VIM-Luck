import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';
import { fmtAmount, fmtDate, confTier, SUPPLIER_FIELD_NAMES, fieldLabel } from '../../src/utils/formatters';
import { hapticSuccess, hapticError, hapticMedium } from '../../src/utils/haptics';
import { calculateRate, getAvailableTransitions, getStatusLabel } from '../../src/services/calculations';
import useInvoiceDetail from '../../src/hooks/useInvoiceDetail';
import SectionCard from '../../src/components/SectionCard';
import FieldRow from '../../src/components/FieldRow';
import LineItemCard from '../../src/components/LineItemCard';
import StatusBadge from '../../src/components/StatusBadge';
import StatusStepper from '../../src/components/StatusStepper';
import FBRBadge from '../../src/components/FBRBadge';
import ClassificationBadge from '../../src/components/ClassificationBadge';
import DuplicateWarning from '../../src/components/DuplicateWarning';
import ApprovalProgressCard from '../../src/components/ApprovalProgressCard';
import CommentsSection from '../../src/components/CommentsSection';
import AuditTrailCard from '../../src/components/AuditTrailCard';
import MultiCurrencyCard from '../../src/components/MultiCurrencyCard';
import POMatchCard from '../../src/components/POMatchCard';

import { SkeletonCard } from '../../src/components/SkeletonLoader';
import type { InvoiceStatus } from '../../src/types';

export default function InvoiceDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const invoiceId = parseInt(id!, 10);

  const {
    invoice,
    loading,
    error,
    editing,
    editLineItems,
    saving,
    startEditing,
    cancelEditing,
    handleLineItemChange,
    saveEdits,
    changeStatus: updateStatus,
    fetchInvoice,
  } = useInvoiceDetail(invoiceId);

  if (loading) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {[1, 2, 3].map((i) => (
          <SkeletonCard key={i} />
        ))}
      </ScrollView>
    );
  }

  if (error || !invoice) {
    return (
      <View style={styles.center}>
        <Ionicons name="alert-circle-outline" size={48} color={colors.danger[400]} />
        <Text style={styles.errorText}>{error || 'Invoice not found.'}</Text>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
          <Text style={styles.backBtnText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const transitions = getAvailableTransitions(invoice.status);
  const lineItems = editing ? editLineItems : invoice.line_items;

  // Build supplier fields from invoice
  const supplierFields = [
    { label: 'Supplier Name', value: invoice.supplier_name, field_name: 'supplier_name' },
    { label: 'NTN / Tax ID', value: invoice.supplier_ntn, field_name: 'supplier_ntn' },
    { label: 'Address', value: invoice.supplier_address, field_name: 'supplier_address' },
  ].filter((f) => f.value);

  // Build invoice header fields
  const invoiceFields = [
    { label: 'Document Type', value: invoice.document_type },
    { label: 'Invoice Number', value: invoice.invoice_number },
    { label: 'Invoice Date', value: fmtDate(invoice.invoice_date) },
    { label: 'Due Date', value: fmtDate(invoice.due_date) },
    { label: 'PO Reference', value: invoice.po_reference },
    { label: 'Receiver', value: invoice.receiver_name },
    { label: 'Receiver Address', value: invoice.receiver_address },
    { label: 'Currency', value: invoice.currency },
    { label: 'Subtotal', value: invoice.subtotal_amount != null ? fmtAmount(invoice.subtotal_amount) : null },
    { label: 'Tax Amount', value: invoice.tax_amount != null ? fmtAmount(invoice.tax_amount) : null },
    { label: 'Total Amount', value: invoice.total_amount != null ? fmtAmount(invoice.total_amount) : null },
  ].filter((f) => f.value);

  // Tax info
  const taxAmount = invoice.tax_amount ?? invoice.gst_amount;
  let subtotal = invoice.subtotal_amount;
  let subtotalSource: string | null = subtotal != null ? 'field' : null;

  if (subtotal == null && lineItems.length > 0) {
    const sum = lineItems.reduce((acc, li) => {
      const amt = parseFloat(String(li.amount));
      return acc + (isNaN(amt) ? 0 : amt);
    }, 0);
    if (sum > 0) {
      subtotal = sum;
      subtotalSource = 'line_items';
    }
  }

  if (subtotal == null && invoice.total_amount != null && taxAmount != null) {
    subtotal = invoice.total_amount - taxAmount;
    subtotalSource = 'derived';
  }

  const taxPct =
    taxAmount != null && subtotal != null && subtotal !== 0
      ? (taxAmount / subtotal) * 100
      : null;

  const handleStatusChange = (newStatus: InvoiceStatus) => {
    const label = getStatusLabel(newStatus);
    Alert.alert('Confirm', `Change status to "${label}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm',
        onPress: async () => {
          try {
            hapticMedium();
            await updateStatus(newStatus);
            hapticSuccess();
          } catch (err: any) {
            hapticError();
            Alert.alert('Error', err?.message || 'Failed to update status.');
          }
        },
      },
    ]);
  };

  const handleSaveEdits = async () => {
    try {
      await saveEdits();
      hapticSuccess();
      Alert.alert('Saved', 'Invoice updated successfully.');
    } catch (err: any) {
      hapticError();
      Alert.alert('Error', err?.message || 'Failed to save.');
    }
  };

  const confLevel = confTier(invoice.overall_confidence);

  return (
    <View style={styles.flex}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.invoiceTitle}>
              {invoice.invoice_number ? `#${invoice.invoice_number}` : `Invoice #${invoice.id}`}
            </Text>
            <Text style={styles.headerSub}>
              {invoice.supplier_name || invoice.original_filename}
            </Text>
          </View>
          <StatusBadge status={invoice.status} />
        </View>

        {/* Status Stepper */}
        <StatusStepper currentStatus={invoice.status} />

        {/* Confidence */}
        {invoice.overall_confidence != null && (
          <View style={styles.confBar}>
            <Text style={styles.confLabel}>Extraction Confidence</Text>
            <Text
              style={[
                styles.confValue,
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
              {invoice.overall_confidence}%
            </Text>
          </View>
        )}

        {/* Duplicate Warning */}
        <DuplicateWarning invoiceId={invoiceId} />

        {/* FBR Verification */}
        {invoice.fbr_verification_status && invoice.fbr_verification_status !== 'not_verified' && (
          <FBRBadge
            verificationStatus={invoice.fbr_verification_status}
            taxpayerName={invoice.fbr_taxpayer_name}
            filingStatus={invoice.fbr_filing_status}
            whtCompliance={invoice.wht_compliance_status}
          />
        )}

        {/* Auto-Classification */}
        <ClassificationBadge invoiceId={invoiceId} currentDocType={invoice.document_type} />

        {/* Approval Workflow */}
        <ApprovalProgressCard
          invoiceId={invoiceId}
          invoiceStatus={invoice.status}
          onStatusChange={() => fetchInvoice?.()}
        />

        {/* Supplier Info */}
        {supplierFields.length > 0 && (
          <SectionCard title="Supplier Information" defaultOpen>
            {supplierFields.map((f) => (
              <FieldRow
                key={f.field_name}
                label={f.label}
                value={f.value!}
                confidence={invoice.field_confidences?.[f.field_name]}
              />
            ))}
          </SectionCard>
        )}

        {/* Invoice Details */}
        {invoiceFields.length > 0 && (
          <SectionCard title="Invoice Details" defaultOpen>
            {invoiceFields.map((f, i) => (
              <FieldRow key={i} label={f.label} value={f.value!} />
            ))}
          </SectionCard>
        )}

        {/* Line Items */}
        <SectionCard
          title={`Line Items (${lineItems.length})`}
          defaultOpen
          headerRight={
            !editing ? (
              <TouchableOpacity onPress={startEditing}>
                <Text style={styles.editLink}>Edit</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity onPress={cancelEditing}>
                <Text style={[styles.editLink, { color: colors.danger[500] }]}>Cancel</Text>
              </TouchableOpacity>
            )
          }
        >
          {lineItems.length === 0 ? (
            <Text style={styles.emptyText}>No line items.</Text>
          ) : (
            lineItems.map((li, idx) => (
              <LineItemCard
                key={li.id ?? idx}
                index={idx}
                item={{
                  description: li.description,
                  quantity: li.quantity,
                  unit: li.unit,
                  unit_price: li.unit_price,
                  amount: li.amount,
                }}
                editing={editing}
                onChange={editing ? handleLineItemChange : undefined}
              />
            ))
          )}
          {editing && (
            <TouchableOpacity style={styles.saveEditBtn} onPress={handleSaveEdits} disabled={saving}>
              {saving ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <>
                  <Ionicons name="save" size={16} color="#fff" />
                  <Text style={styles.saveEditBtnText}>Save Changes</Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </SectionCard>

        {/* Sales Tax */}
        {taxAmount != null && (
          <SectionCard title="Sales Tax" defaultOpen>
            <FieldRow label="Sales Tax Amount" value={fmtAmount(taxAmount)} />
            <FieldRow
              label="Sales Tax %"
              value={taxPct != null ? `${taxPct.toFixed(2)}%` : '—'}
            />
            {subtotal != null && (
              <FieldRow
                label={`Subtotal${
                  subtotalSource === 'line_items'
                    ? ' (from line items)'
                    : subtotalSource === 'derived'
                    ? ' (derived)'
                    : ''
                }`}
                value={fmtAmount(subtotal)}
              />
            )}
            {invoice.total_amount != null && (
              <FieldRow label="Total Amount" value={fmtAmount(invoice.total_amount)} />
            )}
          </SectionCard>
        )}

        {/* PO Matching */}
        <POMatchCard invoiceId={invoiceId} poReference={invoice.po_reference} />

        {/* GL Coding — hidden to match web */}

        {/* Multi-Currency */}
        <MultiCurrencyCard
          currency={invoice.currency}
          baseCurrency={invoice.base_currency}
          exchangeRate={invoice.exchange_rate}
          totalAmount={invoice.total_amount}
          baseTotalAmount={invoice.base_total_amount}
        />

        {/* Comments */}
        <CommentsSection invoiceId={invoiceId} />

        {/* Audit Trail */}
        <AuditTrailCard entityType="invoice" entityId={invoiceId} />

        {/* File Info */}
        <SectionCard title="File Information">
          <FieldRow label="Original File" value={invoice.original_filename} />
          {invoice.file_size_bytes && (
            <FieldRow
              label="File Size"
              value={`${(invoice.file_size_bytes / 1024).toFixed(0)} KB`}
            />
          )}
          {invoice.page_count && (
            <FieldRow label="Pages" value={String(invoice.page_count)} />
          )}
          <FieldRow label="Created" value={fmtDate(invoice.created_at)} />
          {invoice.updated_at && (
            <FieldRow label="Updated" value={fmtDate(invoice.updated_at)} />
          )}
        </SectionCard>

        {/* Spacer for bottom bar */}
        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Bottom Status Actions */}
      {transitions.length > 0 && !editing && (
        <View style={styles.bottomBar}>
          {transitions.map((t) => (
            <TouchableOpacity
              key={t.status}
              style={[
                styles.transitionBtn,
                t.variant === 'primary' && styles.transitionBtnPrimary,
                t.variant === 'danger' && styles.transitionBtnDanger,
              ]}
              onPress={() => handleStatusChange(t.status as InvoiceStatus)}
            >
              <Ionicons
                name={
                  t.status === 'posted'
                    ? 'checkmark-done-circle'
                    : t.status === 'validated'
                    ? 'checkmark-circle'
                    : t.status === 'exception'
                    ? 'alert-circle'
                    : 'arrow-forward-circle'
                }
                size={18}
                color={
                  t.variant === 'primary'
                    ? '#fff'
                    : t.variant === 'danger'
                    ? colors.danger[600]
                    : colors.brand[600]
                }
              />
              <Text
                style={[
                  styles.transitionBtnText,
                  t.variant === 'primary' && styles.transitionBtnTextPrimary,
                  t.variant === 'danger' && styles.transitionBtnTextDanger,
                ]}
              >
                {t.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: {
    flex: 1,
    backgroundColor: colors.neutral[50],
  },
  content: {
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
    marginTop: 12,
    marginBottom: 16,
    textAlign: 'center',
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

  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  headerLeft: {
    flex: 1,
    marginRight: 12,
  },
  invoiceTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.neutral[900],
  },
  headerSub: {
    fontSize: 13,
    color: colors.neutral[500],
    marginTop: 2,
  },

  // Confidence bar
  confBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginBottom: 12,
  },
  confLabel: {
    fontSize: 12,
    color: colors.neutral[500],
    fontWeight: '600',
  },
  confValue: {
    fontSize: 16,
    fontWeight: '700',
  },

  editLink: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.brand[600],
  },

  emptyText: {
    fontSize: 13,
    color: colors.neutral[400],
    textAlign: 'center',
    paddingVertical: 16,
  },

  saveEditBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: colors.brand[600],
    borderRadius: 10,
    paddingVertical: 12,
    marginTop: 12,
  },
  saveEditBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
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
  transitionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.brand[300],
    borderRadius: 10,
  },
  transitionBtnPrimary: {
    backgroundColor: colors.brand[600],
    borderColor: colors.brand[600],
  },
  transitionBtnDanger: {
    borderColor: colors.danger[300],
    backgroundColor: 'transparent',
  },
  transitionBtnText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.brand[600],
  },
  transitionBtnTextPrimary: {
    color: '#fff',
  },
  transitionBtnTextDanger: {
    color: colors.danger[600],
  },
});
