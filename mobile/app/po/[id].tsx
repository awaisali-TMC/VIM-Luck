import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  TextInput,
  Modal,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';
import { fmtAmount, fmtDate } from '../../src/utils/formatters';
import { hapticSuccess, hapticError, hapticMedium } from '../../src/utils/haptics';
import usePODetail from '../../src/hooks/usePODetail';
import {
  createGRN,
  createSES,
  type GRNCreatePayload,
  type SESCreatePayload,
} from '../../src/services/purchaseOrderService';
import SectionCard from '../../src/components/SectionCard';
import FieldRow from '../../src/components/FieldRow';
import { SkeletonCard } from '../../src/components/SkeletonLoader';
import type { POLineItem } from '../../src/types';

const STATUS_ACTIONS: Record<string, string[]> = {
  draft: ['open', 'cancelled'],
  open: ['partially_received', 'fully_received', 'closed', 'cancelled'],
  partially_received: ['fully_received', 'closed'],
  fully_received: ['closed'],
  closed: ['open'],
  cancelled: ['draft'],
};

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  open: 'Open',
  partially_received: 'Partial Recv.',
  fully_received: 'Fully Received',
  closed: 'Closed',
  cancelled: 'Cancelled',
};

export default function PODetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const poId = parseInt(id!, 10);

  const { po, loading, error, changeStatus, fetchPO } = usePODetail(poId);

  // GRN Modal state
  const [grnModalOpen, setGrnModalOpen] = useState(false);
  const [grnNumber, setGrnNumber] = useState('');
  const [grnDate, setGrnDate] = useState('');
  const [grnReceivedBy, setGrnReceivedBy] = useState('');
  const [grnLocation, setGrnLocation] = useState('');
  const [grnNotes, setGrnNotes] = useState('');
  const [grnLines, setGrnLines] = useState<Array<{ po_line_item_id: number; received_quantity: string; inspection_status: string }>>([]);
  const [grnSaving, setGrnSaving] = useState(false);

  // SES Modal state
  const [sesModalOpen, setSesModalOpen] = useState(false);
  const [sesNumber, setSesNumber] = useState('');
  const [sesDate, setSesDate] = useState('');
  const [sesPeriodFrom, setSesPeriodFrom] = useState('');
  const [sesPeriodTo, setSesPeriodTo] = useState('');
  const [sesNotes, setSesNotes] = useState('');
  const [sesLines, setSesLines] = useState<Array<{ po_line_item_id: number; completed_quantity: string; unit_price: number }>>([]);
  const [sesSaving, setSesSaving] = useState(false);

  if (loading) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
      </ScrollView>
    );
  }

  if (error || !po) {
    return (
      <View style={styles.center}>
        <Ionicons name="alert-circle-outline" size={48} color={colors.danger[400]} />
        <Text style={styles.errorText}>{error || 'PO not found.'}</Text>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
          <Text style={styles.backBtnText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const actions = STATUS_ACTIONS[po.status] || [];
  const canAddGRN = ['open', 'partially_received'].includes(po.status) && po.po_type !== 'contract';
  const canAddSES = ['open', 'partially_received'].includes(po.status) && po.po_type === 'contract';

  // Calculate received quantities per PO line
  const receivedMap: Record<number, number> = {};
  (po.grns || []).forEach((grn) => {
    (grn.line_items || []).forEach((gli) => {
      receivedMap[gli.po_line_item_id] = (receivedMap[gli.po_line_item_id] || 0) + gli.received_quantity;
    });
  });
  (po.ses_records || []).forEach((ses) => {
    (ses.line_items || []).forEach((sli) => {
      receivedMap[sli.po_line_item_id] = (receivedMap[sli.po_line_item_id] || 0) + sli.completed_quantity;
    });
  });

  const openGRNModal = () => {
    setGrnNumber('');
    setGrnDate('');
    setGrnReceivedBy('');
    setGrnLocation('');
    setGrnNotes('');
    setGrnLines(
      po.line_items.map((li) => ({
        po_line_item_id: li.id!,
        received_quantity: '0',
        inspection_status: 'accepted',
      })),
    );
    setGrnModalOpen(true);
  };

  const openSESModal = () => {
    setSesNumber('');
    setSesDate('');
    setSesPeriodFrom('');
    setSesPeriodTo('');
    setSesNotes('');
    setSesLines(
      po.line_items.map((li) => ({
        po_line_item_id: li.id!,
        completed_quantity: '0',
        unit_price: li.unit_price,
      })),
    );
    setSesModalOpen(true);
  };

  const saveGRN = async () => {
    if (!grnNumber.trim()) {
      Alert.alert('Validation', 'GRN Number is required.');
      return;
    }
    const validLines = grnLines.filter((l) => parseFloat(l.received_quantity) > 0);
    if (validLines.length === 0) {
      Alert.alert('Validation', 'At least one line must have received quantity > 0.');
      return;
    }
    try {
      setGrnSaving(true);
      const payload: GRNCreatePayload = {
        grn_number: grnNumber.trim(),
        grn_date: grnDate.trim() || undefined,
        received_by: grnReceivedBy.trim() || undefined,
        plant_location: grnLocation.trim() || undefined,
        notes: grnNotes.trim() || undefined,
        line_items: validLines.map((l) => ({
          po_line_item_id: l.po_line_item_id,
          received_quantity: parseFloat(l.received_quantity),
          inspection_status: l.inspection_status,
        })),
      };
      await createGRN(poId, payload);
      hapticSuccess();
      setGrnModalOpen(false);
      fetchPO();
    } catch (err: any) {
      hapticError();
      Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to create GRN.');
    } finally {
      setGrnSaving(false);
    }
  };

  const saveSES = async () => {
    if (!sesNumber.trim()) {
      Alert.alert('Validation', 'SES Number is required.');
      return;
    }
    const validLines = sesLines.filter((l) => parseFloat(l.completed_quantity) > 0);
    if (validLines.length === 0) {
      Alert.alert('Validation', 'At least one line must have completed quantity > 0.');
      return;
    }
    try {
      setSesSaving(true);
      const payload: SESCreatePayload = {
        ses_number: sesNumber.trim(),
        ses_date: sesDate.trim() || undefined,
        service_period_from: sesPeriodFrom.trim() || undefined,
        service_period_to: sesPeriodTo.trim() || undefined,
        notes: sesNotes.trim() || undefined,
        line_items: validLines.map((l) => ({
          po_line_item_id: l.po_line_item_id,
          completed_quantity: parseFloat(l.completed_quantity),
          completed_amount: parseFloat(l.completed_quantity) * l.unit_price,
        })),
      };
      await createSES(poId, payload);
      hapticSuccess();
      setSesModalOpen(false);
      fetchPO();
    } catch (err: any) {
      hapticError();
      Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to create SES.');
    } finally {
      setSesSaving(false);
    }
  };

  const handleStatusChange = (newStatus: string) => {
    Alert.alert('Confirm', `Change status to "${STATUS_LABELS[newStatus] || newStatus}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm',
        onPress: async () => {
          try {
            hapticMedium();
            await changeStatus(newStatus);
            hapticSuccess();
          } catch (err: any) {
            hapticError();
            Alert.alert('Error', err?.message || 'Failed to change status.');
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.flex}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header — matches invoice detail */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.poTitle}>{po.po_number}</Text>
            <Text style={styles.headerSub}>{po.vendor_name}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: getStatusBg(po.status) }]}>
            <Text style={[styles.statusText, { color: getStatusColor(po.status) }]}>
              {STATUS_LABELS[po.status] || po.status}
            </Text>
          </View>
        </View>

        {/* Amount bar — matches invoice confBar style */}
        <View style={styles.amountBar}>
          <Text style={styles.amountBarLabel}>Total Amount</Text>
          <Text style={styles.amountBarValue}>{po.currency} {fmtAmount(po.total_amount)}</Text>
        </View>

        {/* PO Details */}
        <SectionCard title="PO Information" defaultOpen>
          <FieldRow label="PO Number" value={po.po_number} />
          <FieldRow label="Vendor" value={po.vendor_name} />
          {po.vendor_ntn && <FieldRow label="NTN" value={po.vendor_ntn} />}
          <FieldRow label="Type" value={(po.po_type || 'local').charAt(0).toUpperCase() + (po.po_type || 'local').slice(1)} />
          <FieldRow label="Currency" value={po.currency} />
          <FieldRow label="Date" value={fmtDate(po.po_date)} />
          {po.notes && <FieldRow label="Notes" value={po.notes} />}
        </SectionCard>

        {/* Line Items */}
        <SectionCard title={`Line Items (${po.line_items.length})`} defaultOpen>
          {po.line_items.map((li, idx) => {
            const rcvd = receivedMap[li.id!] || 0;
            const pct = li.quantity > 0 ? Math.round((rcvd / li.quantity) * 100) : 0;
            return (
              <View key={li.id ?? idx} style={styles.lineRow}>
                <View style={styles.lineInfo}>
                  <Text style={styles.lineDesc} numberOfLines={2}>
                    {li.description || `Item ${idx + 1}`}
                  </Text>
                  <Text style={styles.lineMeta}>
                    {li.quantity} {li.unit || 'pcs'} x {fmtAmount(li.unit_price)} = {po.currency} {fmtAmount(li.amount)}
                  </Text>
                </View>
                <View style={styles.lineRecv}>
                  <Text style={[styles.recvPct, pct >= 100 && styles.recvFull]}>
                    {pct}%
                  </Text>
                  <Text style={styles.recvLabel}>Recv.</Text>
                </View>
              </View>
            );
          })}
        </SectionCard>

        {/* GRN Section */}
        <SectionCard
          title={`Goods Receipts (${(po.grns || []).length})`}
          headerRight={
            canAddGRN ? (
              <TouchableOpacity onPress={openGRNModal} style={styles.addSmallBtn}>
                <Ionicons name="add" size={16} color={colors.brand[600]} />
                <Text style={styles.addSmallText}>Add GRN</Text>
              </TouchableOpacity>
            ) : undefined
          }
        >
          {(po.grns || []).length === 0 ? (
            <Text style={styles.emptyText}>No goods receipts yet.</Text>
          ) : (
            (po.grns || []).map((grn) => (
              <View key={grn.id} style={styles.subCard}>
                <View style={styles.subHeader}>
                  <Text style={styles.subTitle}>{grn.grn_number}</Text>
                  <Text style={styles.subDate}>{fmtDate(grn.grn_date || grn.created_at)}</Text>
                </View>
                {grn.received_by && <Text style={styles.subMeta}>By: {grn.received_by}</Text>}
                {grn.line_items.map((gli, i) => {
                  const poLine = po.line_items.find((l) => l.id === gli.po_line_item_id);
                  return (
                    <Text key={i} style={styles.subLine}>
                      {poLine?.description || `Item ${gli.po_line_item_id}`}: {gli.received_quantity} qty ({gli.inspection_status || 'accepted'})
                    </Text>
                  );
                })}
              </View>
            ))
          )}
        </SectionCard>

        {/* SES Section */}
        <SectionCard
          title={`Service Entries (${(po.ses_records || []).length})`}
          headerRight={
            canAddSES ? (
              <TouchableOpacity onPress={openSESModal} style={styles.addSmallBtn}>
                <Ionicons name="add" size={16} color={colors.brand[600]} />
                <Text style={styles.addSmallText}>Add SES</Text>
              </TouchableOpacity>
            ) : undefined
          }
        >
          {(po.ses_records || []).length === 0 ? (
            <Text style={styles.emptyText}>No service entries yet.</Text>
          ) : (
            (po.ses_records || []).map((ses) => (
              <View key={ses.id} style={styles.subCard}>
                <View style={styles.subHeader}>
                  <Text style={styles.subTitle}>{ses.ses_number}</Text>
                  <Text style={styles.subDate}>{fmtDate(ses.ses_date || ses.created_at)}</Text>
                </View>
                {ses.service_period_from && (
                  <Text style={styles.subMeta}>
                    Period: {fmtDate(ses.service_period_from)} - {fmtDate(ses.service_period_to)}
                  </Text>
                )}
                {ses.line_items.map((sli, i) => {
                  const poLine = po.line_items.find((l) => l.id === sli.po_line_item_id);
                  return (
                    <Text key={i} style={styles.subLine}>
                      {poLine?.description || `Item ${sli.po_line_item_id}`}: {sli.completed_quantity} qty
                      {sli.completed_amount ? ` (${fmtAmount(sli.completed_amount)})` : ''}
                    </Text>
                  );
                })}
              </View>
            ))
          )}
        </SectionCard>

        {/* File Info */}
        {po.original_filename && (
          <SectionCard title="Source">
            <FieldRow label="Source" value={po.source_type || 'manual'} />
            {po.original_filename && <FieldRow label="File" value={po.original_filename} />}
          </SectionCard>
        )}

        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Bottom Status Actions */}
      {actions.length > 0 && (
        <View style={styles.bottomBar}>
          {actions.slice(0, 3).map((s) => (
            <TouchableOpacity
              key={s}
              style={[
                styles.actionBtn,
                s === 'cancelled' && styles.actionBtnDanger,
              ]}
              onPress={() => handleStatusChange(s)}
            >
              <Text
                style={[
                  styles.actionBtnText,
                  s === 'cancelled' && styles.actionBtnTextDanger,
                ]}
              >
                {STATUS_LABELS[s] || s}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* GRN Modal */}
      <Modal visible={grnModalOpen} animationType="slide" presentationStyle="pageSheet">
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setGrnModalOpen(false)}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Create GRN</Text>
            <TouchableOpacity onPress={saveGRN} disabled={grnSaving}>
              {grnSaving ? (
                <ActivityIndicator size="small" color={colors.brand[600]} />
              ) : (
                <Text style={styles.modalSave}>Save</Text>
              )}
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.modalScroll} contentContainerStyle={styles.modalContent}>
            <Text style={styles.label}>GRN Number *</Text>
            <TextInput style={styles.input} value={grnNumber} onChangeText={setGrnNumber} placeholder="GRN-001" placeholderTextColor={colors.neutral[300]} />

            <Text style={styles.label}>Date</Text>
            <TextInput style={styles.input} value={grnDate} onChangeText={setGrnDate} placeholder="YYYY-MM-DD" placeholderTextColor={colors.neutral[300]} />

            <Text style={styles.label}>Received By</Text>
            <TextInput style={styles.input} value={grnReceivedBy} onChangeText={setGrnReceivedBy} placeholder="Name" placeholderTextColor={colors.neutral[300]} />

            <Text style={styles.label}>Plant Location</Text>
            <TextInput style={styles.input} value={grnLocation} onChangeText={setGrnLocation} placeholder="Location" placeholderTextColor={colors.neutral[300]} />

            <Text style={[styles.sectionTitle, { marginTop: 20 }]}>Line Items</Text>
            {grnLines.map((gl, idx) => {
              const poLine = po.line_items[idx];
              return (
                <View key={idx} style={styles.modalLineCard}>
                  <Text style={styles.modalLineDesc} numberOfLines={1}>
                    {poLine?.description || `Item ${idx + 1}`}
                  </Text>
                  <Text style={styles.modalLineMeta}>
                    PO Qty: {poLine?.quantity} | Already Recv: {receivedMap[poLine?.id!] || 0}
                  </Text>
                  <View style={styles.modalLineRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.lineLabel}>Recv. Qty</Text>
                      <TextInput
                        style={styles.inputSmall}
                        value={gl.received_quantity}
                        onChangeText={(v) => {
                          setGrnLines((prev) => {
                            const u = [...prev];
                            u[idx] = { ...u[idx], received_quantity: v };
                            return u;
                          });
                        }}
                        keyboardType="numeric"
                        placeholderTextColor={colors.neutral[300]}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.lineLabel}>Status</Text>
                      <View style={styles.inspRow}>
                        {['accepted', 'rejected', 'pending'].map((st) => (
                          <TouchableOpacity
                            key={st}
                            style={[
                              styles.inspBtn,
                              gl.inspection_status === st && styles.inspBtnActive,
                            ]}
                            onPress={() => {
                              setGrnLines((prev) => {
                                const u = [...prev];
                                u[idx] = { ...u[idx], inspection_status: st };
                                return u;
                              });
                            }}
                          >
                            <Text
                              style={[
                                styles.inspBtnText,
                                gl.inspection_status === st && styles.inspBtnTextActive,
                              ]}
                            >
                              {st.charAt(0).toUpperCase() + st.slice(1, 4)}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                  </View>
                </View>
              );
            })}
          </ScrollView>
        </View>
      </Modal>

      {/* SES Modal */}
      <Modal visible={sesModalOpen} animationType="slide" presentationStyle="pageSheet">
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setSesModalOpen(false)}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Create SES</Text>
            <TouchableOpacity onPress={saveSES} disabled={sesSaving}>
              {sesSaving ? (
                <ActivityIndicator size="small" color={colors.brand[600]} />
              ) : (
                <Text style={styles.modalSave}>Save</Text>
              )}
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.modalScroll} contentContainerStyle={styles.modalContent}>
            <Text style={styles.label}>SES Number *</Text>
            <TextInput style={styles.input} value={sesNumber} onChangeText={setSesNumber} placeholder="SES-001" placeholderTextColor={colors.neutral[300]} />

            <Text style={styles.label}>Date</Text>
            <TextInput style={styles.input} value={sesDate} onChangeText={setSesDate} placeholder="YYYY-MM-DD" placeholderTextColor={colors.neutral[300]} />

            <Text style={styles.label}>Service Period From</Text>
            <TextInput style={styles.input} value={sesPeriodFrom} onChangeText={setSesPeriodFrom} placeholder="YYYY-MM-DD" placeholderTextColor={colors.neutral[300]} />

            <Text style={styles.label}>Service Period To</Text>
            <TextInput style={styles.input} value={sesPeriodTo} onChangeText={setSesPeriodTo} placeholder="YYYY-MM-DD" placeholderTextColor={colors.neutral[300]} />

            <Text style={[styles.sectionTitle, { marginTop: 20 }]}>Line Items</Text>
            {sesLines.map((sl, idx) => {
              const poLine = po.line_items[idx];
              return (
                <View key={idx} style={styles.modalLineCard}>
                  <Text style={styles.modalLineDesc} numberOfLines={1}>
                    {poLine?.description || `Item ${idx + 1}`}
                  </Text>
                  <Text style={styles.modalLineMeta}>
                    PO Qty: {poLine?.quantity} | Already Completed: {receivedMap[poLine?.id!] || 0}
                  </Text>
                  <View style={{ marginTop: 6 }}>
                    <Text style={styles.lineLabel}>Completed Qty</Text>
                    <TextInput
                      style={styles.inputSmall}
                      value={sl.completed_quantity}
                      onChangeText={(v) => {
                        setSesLines((prev) => {
                          const u = [...prev];
                          u[idx] = { ...u[idx], completed_quantity: v };
                          return u;
                        });
                      }}
                      keyboardType="numeric"
                      placeholderTextColor={colors.neutral[300]}
                    />
                    <Text style={styles.sesAmount}>
                      Amount: {fmtAmount((parseFloat(sl.completed_quantity) || 0) * sl.unit_price)}
                    </Text>
                  </View>
                </View>
              );
            })}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

function getStatusBg(status: string): string {
  const map: Record<string, string> = {
    draft: colors.neutral[100],
    open: colors.info[50],
    partially_received: colors.warning[50],
    fully_received: colors.success[50],
    closed: colors.neutral[200],
    cancelled: colors.danger[50],
  };
  return map[status] || colors.neutral[100];
}

function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    draft: colors.neutral[600],
    open: colors.info[600],
    partially_received: colors.warning[700],
    fully_received: colors.success[700],
    closed: colors.neutral[700],
    cancelled: colors.danger[600],
  };
  return map[status] || colors.neutral[600];
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { flex: 1, backgroundColor: colors.neutral[50] },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  errorText: { fontSize: 15, color: colors.neutral[500], marginTop: 12, marginBottom: 16 },
  backBtn: { paddingHorizontal: 20, paddingVertical: 10, backgroundColor: colors.brand[600], borderRadius: 8 },
  backBtnText: { color: '#fff', fontWeight: '600' },

  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  headerLeft: { flex: 1, marginRight: 12 },
  poTitle: { fontSize: 20, fontWeight: '700', color: colors.neutral[900] },
  headerSub: { fontSize: 13, color: colors.neutral[500], marginTop: 2 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusText: { fontSize: 11, fontWeight: '700' },

  amountBar: {
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
  amountBarLabel: {
    fontSize: 12,
    color: colors.neutral[500],
    fontWeight: '600',
  },
  amountBarValue: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.brand[600],
    fontVariant: ['tabular-nums'],
  },

  lineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  lineInfo: { flex: 1 },
  lineDesc: { fontSize: 13, fontWeight: '600', color: colors.neutral[800] },
  lineMeta: { fontSize: 11, color: colors.neutral[500], marginTop: 2, fontVariant: ['tabular-nums'] },
  lineRecv: { alignItems: 'center', marginLeft: 8 },
  recvPct: { fontSize: 14, fontWeight: '700', color: colors.warning[600] },
  recvFull: { color: colors.success[600] },
  recvLabel: { fontSize: 9, fontWeight: '600', color: colors.neutral[400] },

  addSmallBtn: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  addSmallText: { fontSize: 12, fontWeight: '600', color: colors.brand[600] },

  emptyText: { fontSize: 13, color: colors.neutral[400], textAlign: 'center', paddingVertical: 12 },

  subCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  subHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  subTitle: { fontSize: 13, fontWeight: '700', color: colors.neutral[800] },
  subDate: { fontSize: 11, color: colors.neutral[400] },
  subMeta: { fontSize: 11, color: colors.neutral[500], marginBottom: 4 },
  subLine: { fontSize: 12, color: colors.neutral[600], marginTop: 2 },

  bottomBar: {
    flexDirection: 'row',
    padding: 16,
    paddingBottom: 32,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: colors.neutral[200],
    gap: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.brand[300],
    borderRadius: 10,
    alignItems: 'center',
  },
  actionBtnDanger: { borderColor: colors.danger[300] },
  actionBtnText: { fontSize: 12, fontWeight: '600', color: colors.brand[600] },
  actionBtnTextDanger: { color: colors.danger[600] },

  // Modal styles
  modalContainer: { flex: 1, backgroundColor: '#fff' },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[200],
  },
  modalCancel: { fontSize: 15, color: colors.neutral[500], fontWeight: '500' },
  modalTitle: { fontSize: 17, fontWeight: '700', color: colors.neutral[900] },
  modalSave: { fontSize: 15, color: colors.brand[600], fontWeight: '700' },
  modalScroll: { flex: 1 },
  modalContent: { padding: 16, paddingBottom: 40 },

  label: { fontSize: 12, fontWeight: '600', color: colors.neutral[500], marginBottom: 4, marginTop: 10 },
  input: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: colors.neutral[800],
  },
  inputSmall: {
    backgroundColor: colors.neutral[50],
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 8,
    paddingVertical: 8,
    fontSize: 13,
    color: colors.neutral[800],
  },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: colors.neutral[800], marginBottom: 10 },

  modalLineCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  modalLineDesc: { fontSize: 13, fontWeight: '600', color: colors.neutral[800] },
  modalLineMeta: { fontSize: 11, color: colors.neutral[500], marginTop: 2 },
  modalLineRow: { flexDirection: 'row', gap: 10, marginTop: 8 },

  lineLabel: { fontSize: 10, fontWeight: '600', color: colors.neutral[400], marginBottom: 3 },

  inspRow: { flexDirection: 'row', gap: 4 },
  inspBtn: {
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 6,
    backgroundColor: colors.neutral[100],
  },
  inspBtnActive: { backgroundColor: colors.brand[600] },
  inspBtnText: { fontSize: 10, fontWeight: '600', color: colors.neutral[600] },
  inspBtnTextActive: { color: '#fff' },

  sesAmount: { fontSize: 12, fontWeight: '600', color: colors.brand[600], marginTop: 4 },
});
