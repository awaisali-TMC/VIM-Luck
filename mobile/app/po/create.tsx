import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../../src/utils/colors';
import { hapticSuccess, hapticError } from '../../src/utils/haptics';
import { createPurchaseOrder, type POCreatePayload } from '../../src/services/purchaseOrderService';

interface EditLineItem {
  description: string;
  quantity: string;
  unit: string;
  unit_price: string;
}

export default function POCreateScreen() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);

  // Form fields
  const [poNumber, setPoNumber] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [vendorNtn, setVendorNtn] = useState('');
  const [poDate, setPoDate] = useState('');
  const [poType, setPoType] = useState<'local' | 'foreign' | 'contract'>('local');
  const [currency, setCurrency] = useState('PKR');
  const [notes, setNotes] = useState('');

  // Line items
  const [lineItems, setLineItems] = useState<EditLineItem[]>([
    { description: '', quantity: '1', unit: '', unit_price: '0' },
  ]);

  const updateLineItem = (index: number, field: keyof EditLineItem, value: string) => {
    setLineItems((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const addLineItem = () => {
    setLineItems((prev) => [
      ...prev,
      { description: '', quantity: '1', unit: '', unit_price: '0' },
    ]);
  };

  const removeLineItem = (index: number) => {
    if (lineItems.length <= 1) return;
    setLineItems((prev) => prev.filter((_, i) => i !== index));
  };

  const calcAmount = (li: EditLineItem): number => {
    const qty = parseFloat(li.quantity) || 0;
    const price = parseFloat(li.unit_price) || 0;
    return qty * price;
  };

  const totalAmount = lineItems.reduce((sum, li) => sum + calcAmount(li), 0);

  const handleSave = async () => {
    if (!poNumber.trim()) {
      Alert.alert('Validation', 'PO Number is required.');
      return;
    }
    if (!vendorName.trim()) {
      Alert.alert('Validation', 'Vendor Name is required.');
      return;
    }
    const validLines = lineItems.filter((li) => li.description.trim());
    if (validLines.length === 0) {
      Alert.alert('Validation', 'At least one line item is required.');
      return;
    }

    try {
      setSaving(true);
      const payload: POCreatePayload = {
        po_number: poNumber.trim(),
        vendor_name: vendorName.trim(),
        vendor_ntn: vendorNtn.trim() || undefined,
        po_date: poDate.trim() || undefined,
        po_type: poType,
        currency,
        notes: notes.trim() || undefined,
        line_items: validLines.map((li) => ({
          description: li.description.trim(),
          quantity: parseFloat(li.quantity) || 1,
          unit: li.unit.trim() || undefined,
          unit_price: parseFloat(li.unit_price) || 0,
          amount: calcAmount(li),
        })),
      };
      await createPurchaseOrder(payload);
      hapticSuccess();
      Alert.alert('Success', 'Purchase Order created.', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (err: any) {
      hapticError();
      Alert.alert('Error', err.response?.data?.detail || err.message || 'Failed to create PO.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.flex}>
      <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
        {/* Header — matches app pattern */}
        <View style={styles.headerBar}>
          <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={22} color={colors.neutral[700]} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Create Purchase Order</Text>
          <View style={{ width: 22 }} />
        </View>

        {/* PO Header Fields */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>PO Information</Text>

          <Text style={styles.label}>PO Number *</Text>
          <TextInput
            style={styles.input}
            value={poNumber}
            onChangeText={setPoNumber}
            placeholder="e.g., PO-2026-001"
            placeholderTextColor={colors.neutral[300]}
          />

          <Text style={styles.label}>Vendor Name *</Text>
          <TextInput
            style={styles.input}
            value={vendorName}
            onChangeText={setVendorName}
            placeholder="e.g., Haier Pakistan"
            placeholderTextColor={colors.neutral[300]}
          />

          <Text style={styles.label}>Vendor NTN</Text>
          <TextInput
            style={styles.input}
            value={vendorNtn}
            onChangeText={setVendorNtn}
            placeholder="Tax ID"
            placeholderTextColor={colors.neutral[300]}
          />

          <Text style={styles.label}>PO Date</Text>
          <TextInput
            style={styles.input}
            value={poDate}
            onChangeText={setPoDate}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={colors.neutral[300]}
          />

          {/* PO Type selector */}
          <Text style={styles.label}>PO Type</Text>
          <View style={styles.typeRow}>
            {(['local', 'foreign', 'contract'] as const).map((t) => (
              <TouchableOpacity
                key={t}
                style={[styles.typeBtn, poType === t && styles.typeBtnActive]}
                onPress={() => setPoType(t)}
              >
                <Text
                  style={[styles.typeBtnText, poType === t && styles.typeBtnTextActive]}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Currency selector */}
          <Text style={styles.label}>Currency</Text>
          <View style={styles.typeRow}>
            {['PKR', 'USD', 'EUR', 'GBP'].map((c) => (
              <TouchableOpacity
                key={c}
                style={[styles.typeBtn, currency === c && styles.typeBtnActive]}
                onPress={() => setCurrency(c)}
              >
                <Text
                  style={[styles.typeBtnText, currency === c && styles.typeBtnTextActive]}
                >
                  {c}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.label}>Notes</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            value={notes}
            onChangeText={setNotes}
            placeholder="Optional notes"
            placeholderTextColor={colors.neutral[300]}
            multiline
            numberOfLines={3}
          />
        </View>

        {/* Line Items */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>
              Line Items ({lineItems.length})
            </Text>
            <TouchableOpacity onPress={addLineItem} style={styles.addBtn}>
              <Ionicons name="add-circle" size={20} color={colors.brand[600]} />
              <Text style={styles.addBtnText}>Add</Text>
            </TouchableOpacity>
          </View>

          {lineItems.map((li, idx) => (
            <View key={idx} style={styles.lineCard}>
              <View style={styles.lineHeader}>
                <Text style={styles.lineNum}>#{idx + 1}</Text>
                {lineItems.length > 1 && (
                  <TouchableOpacity onPress={() => removeLineItem(idx)}>
                    <Ionicons name="trash-outline" size={16} color={colors.danger[500]} />
                  </TouchableOpacity>
                )}
              </View>

              <TextInput
                style={styles.input}
                value={li.description}
                onChangeText={(v) => updateLineItem(idx, 'description', v)}
                placeholder="Description"
                placeholderTextColor={colors.neutral[300]}
              />

              <View style={styles.lineRow}>
                <View style={styles.lineField}>
                  <Text style={styles.lineLabel}>Qty</Text>
                  <TextInput
                    style={styles.inputSmall}
                    value={li.quantity}
                    onChangeText={(v) => updateLineItem(idx, 'quantity', v)}
                    keyboardType="numeric"
                    placeholderTextColor={colors.neutral[300]}
                  />
                </View>
                <View style={styles.lineField}>
                  <Text style={styles.lineLabel}>Unit</Text>
                  <TextInput
                    style={styles.inputSmall}
                    value={li.unit}
                    onChangeText={(v) => updateLineItem(idx, 'unit', v)}
                    placeholder="Pcs"
                    placeholderTextColor={colors.neutral[300]}
                  />
                </View>
                <View style={styles.lineField}>
                  <Text style={styles.lineLabel}>Unit Price</Text>
                  <TextInput
                    style={styles.inputSmall}
                    value={li.unit_price}
                    onChangeText={(v) => updateLineItem(idx, 'unit_price', v)}
                    keyboardType="numeric"
                    placeholderTextColor={colors.neutral[300]}
                  />
                </View>
                <View style={styles.lineField}>
                  <Text style={styles.lineLabel}>Amount</Text>
                  <Text style={styles.amountText}>
                    {calcAmount(li).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </Text>
                </View>
              </View>
            </View>
          ))}

          {/* Total */}
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Total</Text>
            <Text style={styles.totalValue}>
              {currency} {totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </Text>
          </View>
        </View>
      </ScrollView>

      {/* Bottom Save */}
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={[styles.cancelBtn]}
          onPress={() => router.back()}
        >
          <Text style={styles.cancelBtnText}>Cancel</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.saveBtn}
          onPress={handleSave}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <>
              <Ionicons name="save" size={16} color="#fff" />
              <Text style={styles.saveBtnText}>Create PO</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.neutral[50] },
  scroll: { flex: 1 },
  content: { paddingBottom: 100 },
  headerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 52,
    paddingBottom: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
  },
  headerTitle: { fontSize: 18, fontWeight: '700', color: colors.neutral[900] },

  section: {
    backgroundColor: '#fff',
    margin: 16,
    marginBottom: 0,
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: colors.neutral[100],
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.neutral[800],
    marginBottom: 12,
  },

  label: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.neutral[500],
    marginBottom: 4,
    marginTop: 10,
  },
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
  multiline: {
    minHeight: 60,
    textAlignVertical: 'top',
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

  typeRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  typeBtn: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 8,
    backgroundColor: colors.neutral[100],
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  typeBtnActive: {
    backgroundColor: colors.brand[600],
    borderColor: colors.brand[600],
  },
  typeBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.neutral[600],
  },
  typeBtnTextActive: {
    color: '#fff',
  },

  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  addBtnText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.brand[600],
  },

  lineCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.neutral[200],
  },
  lineHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  lineNum: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.brand[600],
  },
  lineRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  lineField: { flex: 1 },
  lineLabel: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.neutral[400],
    marginBottom: 3,
  },
  amountText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.neutral[800],
    paddingVertical: 8,
    fontVariant: ['tabular-nums'],
  },

  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.neutral[200],
    marginTop: 4,
  },
  totalLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.neutral[700],
  },
  totalValue: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.brand[600],
    fontVariant: ['tabular-nums'],
  },

  bottomBar: {
    flexDirection: 'row',
    padding: 16,
    paddingBottom: 32,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: colors.neutral[200],
    gap: 10,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.neutral[300],
    borderRadius: 10,
    alignItems: 'center',
  },
  cancelBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.neutral[600],
  },
  saveBtn: {
    flex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    backgroundColor: colors.brand[600],
    borderRadius: 10,
  },
  saveBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
});
