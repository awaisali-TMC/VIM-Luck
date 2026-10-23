import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from '../utils/colors';
import { fmtAmount } from '../utils/formatters';
import { calculateRate } from '../services/calculations';

interface LineItemData {
  description: string | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  amount: number | null;
}

interface Props {
  index: number;
  item: LineItemData;
  editing?: boolean;
  onChange?: (index: number, field: string, value: number | string | null) => void;
}

export default function LineItemCard({
  index,
  item,
  editing: externalEditing,
  onChange,
}: Props) {
  const [localEditing, setLocalEditing] = useState(false);
  const editing = externalEditing ?? localEditing;
  const [editQty, setEditQty] = useState(item.quantity?.toString() ?? '');
  const [editAmt, setEditAmt] = useState(item.amount?.toString() ?? '');
  const [editDesc, setEditDesc] = useState(item.description ?? '');

  useEffect(() => {
    setEditQty(item.quantity?.toString() ?? '');
    setEditAmt(item.amount?.toString() ?? '');
    setEditDesc(item.description ?? '');
  }, [item.quantity, item.amount, item.description]);

  const commitQty = () => {
    const val = parseFloat(editQty);
    if (!isNaN(val) && onChange) onChange(index, 'quantity', val);
  };

  const commitAmt = () => {
    const val = parseFloat(editAmt);
    if (!isNaN(val) && onChange) onChange(index, 'amount', val);
  };

  const commitDesc = () => {
    if (onChange) onChange(index, 'description', editDesc);
  };

  const displayRate =
    item.quantity && item.amount ? calculateRate(item.amount, item.quantity) : item.unit_price;

  // ─── Edit mode ──────────────────────────────────────
  if (editing) {
    return (
      <View style={styles.editCard}>
        <Text style={styles.editIndex}>Item #{index + 1}</Text>
        <View style={styles.editBody}>
          <Text style={styles.editLabel}>Description</Text>
          <TextInput
            style={styles.editInput}
            value={editDesc}
            onChangeText={setEditDesc}
            onBlur={commitDesc}
            placeholder="Description"
            placeholderTextColor={colors.neutral[300]}
          />
          <View style={styles.editRow}>
            <View style={styles.editField}>
              <Text style={styles.editLabel}>Qty</Text>
              <TextInput
                style={styles.editInput}
                value={editQty}
                onChangeText={setEditQty}
                onBlur={commitQty}
                keyboardType="decimal-pad"
                selectTextOnFocus
              />
            </View>
            <View style={styles.editField}>
              <Text style={styles.editLabel}>Rate</Text>
              <Text style={styles.editReadonly}>{fmtAmount(displayRate)}</Text>
            </View>
            <View style={styles.editField}>
              <Text style={styles.editLabel}>Amount</Text>
              <TextInput
                style={[styles.editInput, { fontWeight: '700' }]}
                value={editAmt}
                onChangeText={setEditAmt}
                onBlur={commitAmt}
                keyboardType="decimal-pad"
                selectTextOnFocus
              />
            </View>
          </View>
          {externalEditing == null && (
            <TouchableOpacity style={styles.saveBtn} onPress={() => setLocalEditing(false)} activeOpacity={0.7}>
              <Ionicons name="checkmark" size={15} color="#fff" />
              <Text style={styles.saveBtnText}>Save</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  }

  // ─── Read-only compact mode ─────────────────────────
  const qtyStr = item.quantity != null ? String(item.quantity) : '—';
  const unitStr = item.unit ? ` ${item.unit}` : '';

  const Wrapper = onChange ? TouchableOpacity : View;

  return (
    <Wrapper style={styles.row} {...(onChange ? { activeOpacity: 0.6, onPress: () => setLocalEditing(true) } : {})}>
      <Text style={styles.rowIndex}>{index + 1}</Text>
      <View style={styles.rowBody}>
        <Text style={styles.rowDesc} numberOfLines={1}>
          {item.description || '—'}
        </Text>
        <Text style={styles.rowDetail}>
          {qtyStr}{unitStr} × {fmtAmount(displayRate)}
        </Text>
      </View>
      <Text style={styles.rowAmount}>{fmtAmount(item.amount)}</Text>
      {onChange && (
        <Ionicons name="chevron-forward" size={14} color={colors.neutral[200]} />
      )}
    </Wrapper>
  );
}

const styles = StyleSheet.create({
  // ── Compact read-only row ──
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.neutral[100],
    gap: 10,
  },
  rowIndex: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.neutral[400],
    width: 18,
    textAlign: 'center',
  },
  rowBody: {
    flex: 1,
  },
  rowDesc: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.neutral[800],
    marginBottom: 3,
  },
  rowDetail: {
    fontSize: 12,
    color: colors.neutral[400],
    fontVariant: ['tabular-nums'],
  },
  rowAmount: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.brand[600],
    fontVariant: ['tabular-nums'],
    textAlign: 'right',
  },

  // ── Edit mode card ──
  editCard: {
    backgroundColor: colors.neutral[50],
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: colors.brand[100],
  },
  editIndex: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.neutral[500],
    marginBottom: 8,
  },
  editBody: {
    flex: 1,
  },
  editLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: colors.neutral[400],
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 3,
  },
  editInput: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.neutral[800],
    backgroundColor: '#fff',
    borderRadius: 6,
    borderWidth: 1,
    borderColor: colors.neutral[200],
    paddingHorizontal: 8,
    paddingVertical: 6,
    marginBottom: 8,
  },
  editRow: {
    flexDirection: 'row',
    gap: 8,
  },
  editField: {
    flex: 1,
  },
  saveBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    backgroundColor: colors.brand[600],
    borderRadius: 8,
    paddingVertical: 8,
    marginTop: 4,
  },
  saveBtnText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
  },
  editReadonly: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.neutral[400],
    backgroundColor: colors.neutral[50],
    borderRadius: 6,
    borderWidth: 1,
    borderColor: colors.neutral[100],
    paddingHorizontal: 8,
    paddingVertical: 6,
    marginBottom: 8,
    fontVariant: ['tabular-nums'],
  },
});
