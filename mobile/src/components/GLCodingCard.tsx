import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { fmtAmount } from '../utils/formatters';
import {
  getGLAccounts,
  getGLAssignments,
  createGLAssignment,
  deleteGLAssignment,
} from '../services/glAccountService';
import type { GLAccount, GLAssignment, LineItem } from '../types';

interface Props {
  invoiceId: number;
  lineItems: LineItem[];
}

export default function GLCodingCard({ invoiceId, lineItems }: Props) {
  const [assignments, setAssignments] = useState<GLAssignment[]>([]);
  const [accounts, setAccounts] = useState<GLAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);

  // Add form
  const [selectedAccountCode, setSelectedAccountCode] = useState('');
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null);
  const [amount, setAmount] = useState('');
  const [costCenter, setCostCenter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showAccountDropdown, setShowAccountDropdown] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [accts, assigns] = await Promise.all([
        getGLAccounts(0, 200),
        getGLAssignments(invoiceId),
      ]);
      setAccounts(accts.accounts || []);
      setAssignments(Array.isArray(assigns) ? assigns : []);
    } catch {}
    finally { setLoading(false); }
  }, [invoiceId]);

  useEffect(() => { loadData(); }, [loadData]);

  const filteredAccounts = accounts.filter(
    (a) =>
      a.is_active === 1 &&
      (searchQuery.length < 1 ||
        a.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.name.toLowerCase().includes(searchQuery.toLowerCase())),
  );

  const handleAdd = async () => {
    if (!selectedAccountCode) {
      Alert.alert('Validation', 'Select a GL account.');
      return;
    }
    try {
      setSaving(true);
      await createGLAssignment({
        invoice_id: invoiceId,
        line_item_id: selectedLineId,
        gl_code: selectedAccountCode,
        amount: amount ? parseFloat(amount) : null,
        cost_center: costCenter.trim() || null,
        assignment_type: 'manual',
      });
      await loadData();
      resetForm();
    } catch (err: any) {
      Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to add assignment.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (id: number) => {
    Alert.alert('Remove Assignment', 'Delete this GL assignment?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteGLAssignment(id);
            await loadData();
          } catch (err: any) {
            Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to delete.');
          }
        },
      },
    ]);
  };

  const resetForm = () => {
    setAdding(false);
    setSelectedAccountCode('');
    setSelectedLineId(null);
    setAmount('');
    setCostCenter('');
    setSearchQuery('');
    setShowAccountDropdown(false);
  };

  // Group assignments
  const headerAssignments = assignments.filter((a) => a.line_item_id == null);
  const lineAssignments = assignments.filter((a) => a.line_item_id != null);
  const lineGrouped: Record<number, GLAssignment[]> = {};
  lineAssignments.forEach((a) => {
    const key = a.line_item_id!;
    if (!lineGrouped[key]) lineGrouped[key] = [];
    lineGrouped[key].push(a);
  });

  return (
    <View style={styles.card}>
      <TouchableOpacity style={styles.header} onPress={() => setExpanded(!expanded)}>
        <View style={styles.headerLeft}>
          <Ionicons name="calculator-outline" size={18} color={colors.brand[500]} />
          <Text style={styles.title}>GL Coding</Text>
          {assignments.length > 0 && (
            <View style={[styles.countBadge, { backgroundColor: colors.brand[100] }]}>
              <Text style={[styles.countText, { color: colors.brand[700] }]}>
                {assignments.length}
              </Text>
            </View>
          )}
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={colors.neutral[400]}
        />
      </TouchableOpacity>

      {expanded && (
        <View style={styles.body}>
          {loading ? (
            <ActivityIndicator size="small" color={colors.brand[500]} style={{ paddingVertical: 12 }} />
          ) : (
            <>
              {/* Header-level assignments */}
              {headerAssignments.length > 0 && (
                <View style={styles.groupSection}>
                  <Text style={styles.groupLabel}>Header Level</Text>
                  {headerAssignments.map((a) => (
                    <View key={a.id} style={styles.assignRow}>
                      <View style={styles.assignInfo}>
                        <Text style={styles.glCode}>{a.gl_code}</Text>
                        <Text style={styles.glName}>{a.gl_name}</Text>
                        {a.cost_center && (
                          <View style={styles.ccPill}>
                            <Text style={styles.ccText}>CC: {a.cost_center}</Text>
                          </View>
                        )}
                      </View>
                      <View style={styles.assignRight}>
                        {a.amount != null && (
                          <Text style={styles.assignAmount}>{fmtAmount(a.amount)}</Text>
                        )}
                        <TouchableOpacity onPress={() => handleDelete(a.id)}>
                          <Ionicons name="trash-outline" size={14} color={colors.danger[400]} />
                        </TouchableOpacity>
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {/* Line-level assignments */}
              {Object.keys(lineGrouped).length > 0 && (
                <View style={styles.groupSection}>
                  <Text style={styles.groupLabel}>Line Items</Text>
                  {Object.entries(lineGrouped).map(([lineId, assigns]) => {
                    const li = lineItems.find((l) => l.id === parseInt(lineId));
                    return (
                      <View key={lineId} style={styles.lineGroup}>
                        <Text style={styles.lineGroupTitle} numberOfLines={1}>
                          {li?.description || `Line #${lineId}`}
                        </Text>
                        {assigns.map((a) => (
                          <View key={a.id} style={styles.assignRowIndented}>
                            <View style={styles.assignInfo}>
                              <Text style={styles.glCode}>{a.gl_code}</Text>
                              <Text style={styles.glName}>{a.gl_name}</Text>
                            </View>
                            <View style={styles.assignRight}>
                              {a.amount != null && (
                                <Text style={styles.assignAmount}>{fmtAmount(a.amount)}</Text>
                              )}
                              <TouchableOpacity onPress={() => handleDelete(a.id)}>
                                <Ionicons name="trash-outline" size={14} color={colors.danger[400]} />
                              </TouchableOpacity>
                            </View>
                          </View>
                        ))}
                      </View>
                    );
                  })}
                </View>
              )}

              {assignments.length === 0 && !adding && (
                <Text style={styles.emptyText}>No GL assignments yet.</Text>
              )}

              {/* Add Form */}
              {adding ? (
                <View style={styles.addForm}>
                  <Text style={styles.formLabel}>GL Account</Text>
                  <TextInput
                    style={styles.input}
                    value={searchQuery}
                    onChangeText={(v) => {
                      setSearchQuery(v);
                      setShowAccountDropdown(true);
                    }}
                    placeholder="Search code or name..."
                    placeholderTextColor={colors.neutral[300]}
                    onFocus={() => setShowAccountDropdown(true)}
                  />
                  {showAccountDropdown && filteredAccounts.length > 0 && (
                    <View style={styles.dropdown}>
                      {filteredAccounts.slice(0, 6).map((a) => (
                        <TouchableOpacity
                          key={a.id}
                          style={styles.dropdownItem}
                          onPress={() => {
                            setSelectedAccountCode(a.code);
                            setSearchQuery(`${a.code} - ${a.name}`);
                            setShowAccountDropdown(false);
                            if (a.cost_center) setCostCenter(a.cost_center);
                          }}
                        >
                          <Text style={styles.dropdownCode}>{a.code}</Text>
                          <Text style={styles.dropdownName}>{a.name}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  )}

                  <Text style={styles.formLabel}>Line Item (optional)</Text>
                  <View style={styles.lineSelect}>
                    <TouchableOpacity
                      style={[styles.lineOption, selectedLineId == null && styles.lineOptionActive]}
                      onPress={() => setSelectedLineId(null)}
                    >
                      <Text style={[styles.lineOptionText, selectedLineId == null && styles.lineOptionTextActive]}>
                        Header
                      </Text>
                    </TouchableOpacity>
                    {lineItems.slice(0, 5).map((li) => (
                      <TouchableOpacity
                        key={li.id}
                        style={[styles.lineOption, selectedLineId === li.id && styles.lineOptionActive]}
                        onPress={() => setSelectedLineId(li.id!)}
                      >
                        <Text
                          style={[styles.lineOptionText, selectedLineId === li.id && styles.lineOptionTextActive]}
                          numberOfLines={1}
                        >
                          {li.description?.slice(0, 20) || `#${li.id}`}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>

                  <View style={styles.formRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.formLabel}>Amount</Text>
                      <TextInput
                        style={styles.input}
                        value={amount}
                        onChangeText={setAmount}
                        keyboardType="numeric"
                        placeholder="Optional"
                        placeholderTextColor={colors.neutral[300]}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.formLabel}>Cost Center</Text>
                      <TextInput
                        style={styles.input}
                        value={costCenter}
                        onChangeText={setCostCenter}
                        placeholder="Optional"
                        placeholderTextColor={colors.neutral[300]}
                      />
                    </View>
                  </View>

                  <View style={styles.formActions}>
                    <TouchableOpacity style={styles.cancelBtn} onPress={resetForm}>
                      <Text style={styles.cancelBtnText}>Cancel</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.saveBtn}
                      onPress={handleAdd}
                      disabled={saving}
                    >
                      {saving ? (
                        <ActivityIndicator size="small" color="#fff" />
                      ) : (
                        <Text style={styles.saveBtnText}>Add</Text>
                      )}
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <TouchableOpacity style={styles.addTrigger} onPress={() => setAdding(true)}>
                  <Ionicons name="add-circle" size={16} color={colors.brand[600]} />
                  <Text style={styles.addTriggerText}>Add GL Assignment</Text>
                </TouchableOpacity>
              )}
            </>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.neutral[100],
    marginBottom: 12,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 14, fontWeight: '700', color: colors.neutral[800] },
  countBadge: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: 8 },
  countText: { fontSize: 10, fontWeight: '700' },

  body: { padding: 14, paddingTop: 0 },
  emptyText: { fontSize: 13, color: colors.neutral[400], textAlign: 'center', paddingVertical: 12 },

  groupSection: { marginBottom: 12 },
  groupLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.neutral[500],
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },

  assignRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  assignRowIndented: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingLeft: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  assignInfo: { flex: 1 },
  glCode: { fontSize: 12, fontWeight: '700', color: colors.brand[600], fontVariant: ['tabular-nums'] },
  glName: { fontSize: 11, color: colors.neutral[600] },
  ccPill: {
    backgroundColor: colors.neutral[100],
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 6,
    alignSelf: 'flex-start',
    marginTop: 2,
  },
  ccText: { fontSize: 9, fontWeight: '600', color: colors.neutral[500] },

  assignRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginLeft: 8,
  },
  assignAmount: { fontSize: 12, fontWeight: '600', color: colors.neutral[700], fontVariant: ['tabular-nums'] },

  lineGroup: { marginBottom: 8 },
  lineGroupTitle: { fontSize: 12, fontWeight: '600', color: colors.neutral[700], marginBottom: 4 },

  addTrigger: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.brand[300],
    borderRadius: 10,
  },
  addTriggerText: { fontSize: 13, fontWeight: '600', color: colors.brand[600] },

  addForm: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  formLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.neutral[500],
    marginBottom: 4,
    marginTop: 8,
  },
  input: {
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 13,
    color: colors.neutral[800],
  },
  dropdown: {
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    marginTop: 2,
  },
  dropdownItem: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  dropdownCode: { fontSize: 12, fontWeight: '700', color: colors.brand[600] },
  dropdownName: { fontSize: 11, color: colors.neutral[500] },

  lineSelect: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 4,
  },
  lineOption: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  lineOptionActive: { backgroundColor: colors.brand[600], borderColor: colors.brand[600] },
  lineOptionText: { fontSize: 11, fontWeight: '600', color: colors.neutral[600] },
  lineOptionTextActive: { color: '#fff' },

  formRow: { flexDirection: 'row', gap: 10 },

  formActions: { flexDirection: 'row', gap: 8, marginTop: 12 },
  cancelBtn: {
    flex: 1,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.neutral[300],
    borderRadius: 8,
    alignItems: 'center',
  },
  cancelBtnText: { fontSize: 13, fontWeight: '600', color: colors.neutral[600] },
  saveBtn: {
    flex: 1,
    paddingVertical: 10,
    backgroundColor: colors.brand[600],
    borderRadius: 8,
    alignItems: 'center',
  },
  saveBtnText: { fontSize: 13, fontWeight: '700', color: '#fff' },
});
